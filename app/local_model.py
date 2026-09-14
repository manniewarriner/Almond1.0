"""Lifecycle management for Almond's bundled local llama.cpp server."""

from __future__ import annotations

import http.client
import os
import subprocess
import time
from pathlib import Path

from app.errors import ProviderError

LOOPBACK_HOST = "127.0.0.1"
LOCAL_MODEL_PORT = 11435
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_EXE = PROJECT_ROOT / "runtime" / "llama.cpp" / "llama-server.exe"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "runtime" / "models"


class LocalModelServer:
    """Start one fixed executable with fixed, non-shell arguments."""

    def __init__(
        self,
        model_file: str,
        server_exe: Path = DEFAULT_SERVER_EXE,
        models_dir: Path = DEFAULT_MODELS_DIR,
    ) -> None:
        self.server_exe = server_exe.resolve()
        self.model_path = (models_dir / model_file).resolve()
        self._process: subprocess.Popen | None = None

    @staticmethod
    def is_ready() -> bool:
        connection = http.client.HTTPConnection(LOOPBACK_HOST, LOCAL_MODEL_PORT, timeout=1)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            response.read()
            return response.status == 200
        except OSError:
            return False
        finally:
            connection.close()

    def start(self, timeout_seconds: int = 120) -> None:
        if self.is_ready():
            return
        if not self.server_exe.is_file():
            raise ProviderError("The bundled llama.cpp runtime is missing.")
        if not self.model_path.is_file():
            raise ProviderError(f"The local model file is missing: {self.model_path.name}")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        threads = max(2, min(4, os.cpu_count() or 2))
        self._process = subprocess.Popen(
            [
                str(self.server_exe),
                "--model",
                str(self.model_path),
                "--host",
                LOOPBACK_HOST,
                "--port",
                str(LOCAL_MODEL_PORT),
                "--ctx-size",
                "4096",
                "--threads",
                str(threads),
                "--jinja",
            ],
            cwd=self.server_exe.parent,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_ready():
                return
            if self._process.poll() is not None:
                raise ProviderError("The local model server failed to start.")
            time.sleep(0.25)
        self.stop()
        raise ProviderError("The local model took too long to start.")

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
