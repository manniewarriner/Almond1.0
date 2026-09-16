"""Lifecycle management for Almond's bundled local llama.cpp server."""

from __future__ import annotations

import asyncio
import http.client
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app.errors import ProviderError

LOOPBACK_HOST = "127.0.0.1"
LOCAL_MODEL_PORT = 11435
# A second, dedicated llama-server instance for Document-bot AI formatting
# (see almond_ai/models/provider.py's document_provider wiring) runs
# alongside the chat model's server on this port, never the same one.
LOCAL_DOC_MODEL_PORT = 11436
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_EXE = PROJECT_ROOT / "runtime" / "llama.cpp" / "llama-server.exe"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "runtime" / "models"


def resolve_model_path(model_file: str, models_dir: Path) -> Path:
    """Resolve model_file inside models_dir, rejecting any attempt to escape it."""
    candidate = Path(model_file)
    if candidate.is_absolute() or candidate.drive:
        raise ProviderError(
            f"Invalid local model file {model_file!r}: must not be an absolute path"
        )
    if ".." in candidate.parts:
        raise ProviderError(f"Invalid local model file {model_file!r}: must not contain '..'")

    models_dir = models_dir.resolve()
    resolved = (models_dir / candidate).resolve()
    try:
        resolved.relative_to(models_dir)
    except ValueError as exc:
        raise ProviderError(
            f"Invalid local model file {model_file!r}: resolves outside the models directory"
        ) from exc
    return resolved


class LocalModelServer:
    """Start one fixed executable with fixed, non-shell arguments."""

    def __init__(
        self,
        model_file: str,
        server_exe: Path = DEFAULT_SERVER_EXE,
        models_dir: Path = DEFAULT_MODELS_DIR,
        port: int = LOCAL_MODEL_PORT,
    ) -> None:
        self.server_exe = server_exe.resolve()
        self.models_dir = models_dir.resolve()
        self.model_path = resolve_model_path(model_file, self.models_dir)
        self.port = port
        self._process: subprocess.Popen | None = None
        # Where this instance's llama-server stderr lands (see _spawn) --
        # port-scoped so the chat and document servers never clobber each
        # other's log when both run at once.
        self._stderr_log = Path(tempfile.gettempdir()) / f"almond-llama-server-{self.port}.log"
        # Guards start()/astart() end-to-end (is_ready check through spawn):
        # the desktop app can run one worker thread per chat bot, and more
        # than one can call start() concurrently while the server is still
        # cold. Without this lock, two threads can both observe
        # is_ready() == False and both spawn a server process -- the second
        # spawn typically fails to bind the port, and the second assignment
        # to self._process silently orphans the first (never tracked,
        # never stopped).
        self._start_lock = threading.Lock()

    def is_ready(self) -> bool:
        connection = http.client.HTTPConnection(LOOPBACK_HOST, self.port, timeout=1)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            response.read()
            return response.status == 200
        except OSError:
            return False
        finally:
            connection.close()

    def _preflight(self) -> None:
        if not self.server_exe.is_file():
            raise ProviderError("The bundled llama.cpp runtime is missing.")
        if not self.model_path.is_file():
            raise ProviderError(f"The local model file is missing: {self.model_path.name}")

    def _spawn(self) -> subprocess.Popen:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cpu_count = os.cpu_count() or 2
        threads = max(2, cpu_count)
        # Captured to a file (not subprocess.PIPE) so a long-lived, healthy
        # server can never deadlock on a full, unread pipe buffer -- only
        # read back if start() below sees the process exit early.
        with self._stderr_log.open("wb") as stderr_file:
            return subprocess.Popen(
                [
                    str(self.server_exe),
                    "--model",
                    str(self.model_path),
                    "--host",
                    LOOPBACK_HOST,
                    "--port",
                    str(self.port),
                    "--ctx-size",
                    "4096",
                    "--threads",
                    str(threads),
                    "--threads-batch",
                    str(threads),
                    "--flash-attn",
                    "on",
                    "--jinja",
                ],
                cwd=self.server_exe.parent,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
                creationflags=creation_flags,
            )

    def _startup_failure_detail(self) -> str:
        """The last logged line from a server process that exited during
        startup -- llama.cpp reports the real reason there (a corrupted or
        incomplete model file, an OOM, a bad flag), which DEVNULL used to
        discard entirely, leaving only a generic "failed to start" with no
        way to diagnose it short of re-running the exe by hand outside the
        app.
        """
        try:
            text = self._stderr_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1][-300:] if lines else ""

    def _startup_failure_message(self) -> str:
        detail = self._startup_failure_detail()
        return (
            f"The local model server failed to start: {detail}"
            if detail
            else "The local model server failed to start."
        )

    def start(self, timeout_seconds: int = 120) -> None:
        """Spawn the server and block the calling thread until it's ready.

        Fine for callers that are already off the main thread (e.g. a chat
        request already running via asyncio.to_thread). A caller that needs
        to keep an event loop -- and anything it's driving, like a Textual
        render loop -- responsive during the wait should use astart()
        instead.

        Serialized on `_start_lock` so that two callers racing in from
        different threads (e.g. the desktop app's per-bot worker threads,
        each starting a chat while the model is still cold) can't both
        observe is_ready() == False and both spawn a server process.
        """
        with self._start_lock:
            if self.is_ready():
                return
            self._preflight()
            self._process = self._spawn()
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if self.is_ready():
                    return
                if self._process.poll() is not None:
                    raise ProviderError(self._startup_failure_message())
                time.sleep(0.25)
            self.stop()
            raise ProviderError("The local model took too long to start.")

    async def astart(self, timeout_seconds: int = 120) -> None:
        """Cooperative-async equivalent of start().

        Spawns the same subprocess the same way, but polls readiness with
        `await asyncio.sleep(...)` between checks instead of a blocking
        `time.sleep(...)` inside a worker thread. That guarantees the
        caller's event loop gets control back between every check, so a UI
        driven by that loop (e.g. a Textual splash screen) keeps rendering
        for the full ~1-2 minutes a cold model load takes, instead of
        appearing frozen.

        Shares `_start_lock` with start() (acquired off-thread so the
        awaiting event loop isn't blocked) so an async and a sync caller
        can never race into a double spawn either.
        """
        await asyncio.to_thread(self._start_lock.acquire)
        try:
            if await asyncio.to_thread(self.is_ready):
                return
            self._preflight()
            self._process = await asyncio.to_thread(self._spawn)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                if await asyncio.to_thread(self.is_ready):
                    return
                if self._process.poll() is not None:
                    raise ProviderError(self._startup_failure_message())
                await asyncio.sleep(0.25)
            await asyncio.to_thread(self.stop)
            raise ProviderError("The local model took too long to start.")
        finally:
            self._start_lock.release()

    def stop(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        finally:
            self._process = None
