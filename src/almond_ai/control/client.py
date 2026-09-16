"""Synchronous client for the Almond control bridge, used by `almond ctl`.

Discovers a running instance from the runtime metadata/token files
under ``<data_dir>/runtime`` (written by `almond_ai.control.server`),
then speaks the same newline-delimited-JSON protocol over a loopback
TCP connection. Every call is a fresh connection: this is a developer
CLI making occasional calls, not a long-lived client needing connection
pooling.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from almond_ai.control.models import ControlResponse
from almond_ai.control.protocol import MAX_REQUEST_BYTES, PROTOCOL_VERSION

HOST = "127.0.0.1"


class ControlUnavailableError(RuntimeError):
    """No running Almond instance with the control bridge enabled was found."""


class ControlAuthError(RuntimeError):
    """The stored control token was rejected by the running instance."""


@dataclass(frozen=True)
class RuntimeHandle:
    pid: int
    instance_id: str
    port: int
    started_at: float
    protocol_version: int
    token: str


def _runtime_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "runtime"


def discover(data_dir: Path) -> RuntimeHandle:
    """Read the running instance's connection details from disk.

    Both files are written together on startup and removed together on
    shutdown (see ControlServer._write_runtime_files/_cleanup_runtime_files),
    so a metadata file with no token, or vice versa, means a shutdown
    raced this read -- treated the same as "not running".
    """
    directory = _runtime_dir(data_dir)
    metadata_path = directory / "control.json"
    token_path = directory / "control-token"
    if not metadata_path.is_file() or not token_path.is_file():
        raise ControlUnavailableError(
            "No running Almond control bridge found. Start Almond with "
            "ALMOND_DEV_CONTROL_ENABLED=true and try again."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ControlUnavailableError(f"Could not read control runtime files: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ControlUnavailableError(f"Corrupt control runtime metadata: {exc}") from exc
    try:
        return RuntimeHandle(token=token, **metadata)
    except TypeError as exc:
        raise ControlUnavailableError(f"Unrecognised control runtime metadata: {exc}") from exc


class ControlClient:
    def __init__(self, handle: RuntimeHandle) -> None:
        self.handle = handle

    async def _call_async(self, action: str, payload: dict | None) -> ControlResponse:
        reader, writer = await asyncio.open_connection(HOST, self.handle.port)
        try:
            request = {
                "version": PROTOCOL_VERSION,
                "request_id": f"ctl-{time.time_ns()}",
                "action": action,
                "token": self.handle.token,
                "payload": payload or {},
            }
            data = (json.dumps(request) + "\n").encode("utf-8")
            if len(data) > MAX_REQUEST_BYTES:
                raise ValueError("Request exceeds 64 KB limit")
            writer.write(data)
            await writer.drain()
            line = await reader.readline()
            if not line:
                raise ControlUnavailableError("Connection closed before a response was received")
            return ControlResponse.model_validate_json(line)
        finally:
            writer.close()

    def call(self, action: str, payload: dict | None = None) -> ControlResponse:
        try:
            response = asyncio.run(self._call_async(action, payload))
        except (ConnectionRefusedError, OSError) as exc:
            raise ControlUnavailableError(f"Could not connect to Almond: {exc}") from exc
        if not response.ok and response.error is not None and response.error.code == "auth_failed":
            raise ControlAuthError(response.error.message)
        return response

    def wait_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                response = self.call("wait_ready")
            except ControlUnavailableError:
                response = None
            ready = response is not None and response.ok and response.result
            if ready and response.result.get("ready"):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(1.0)
