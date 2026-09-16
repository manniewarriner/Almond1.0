"""Local-only control server for the Almond developer console.

Binds strictly to 127.0.0.1 on an OS-assigned ephemeral port -- never
0.0.0.0, never a LAN address. A random per-instance token, generated
fresh on every start, gates every request; the token and connection
metadata live in disk files under ``<data_dir>/runtime`` that are
deleted on shutdown, so a stale file can never make `almond ctl`
believe a dead process is still running.

A Windows named pipe was the first choice for this transport. asyncio's
Windows named-pipe support turned out to be a low-level, protocol-based
API (`ProactorEventLoop.start_serving_pipe`) rather than the plain
stream API (`asyncio.start_server`) used everywhere else in this
module, so this uses the loopback-only TCP socket the design explicitly
allows as a fallback -- it keeps the whole transport small enough to
read in one sitting.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from almond_ai.control import protocol
from almond_ai.control.models import ControlError, ControlResponse

if TYPE_CHECKING:
    from almond_ai.control.dispatcher import ApplicationDispatcher

HOST = "127.0.0.1"


class ControlServer:
    """Owns one asyncio TCP listener plus its runtime metadata/token files."""

    def __init__(self, dispatcher: ApplicationDispatcher, runtime_dir: Path) -> None:
        self.dispatcher = dispatcher
        self.runtime_dir = Path(runtime_dir)
        self._server: asyncio.Server | None = None
        self._token = secrets.token_hex(32)
        self._instance_id = str(uuid.uuid4())
        self.metadata_path = self.runtime_dir / "control.json"
        self.token_path = self.runtime_dir / "control-token"

    @property
    def port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("Control server is not listening")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, host=HOST, port=0, limit=protocol.MAX_REQUEST_BYTES
        )
        self._write_runtime_files()

    async def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        self._cleanup_runtime_files()

    # -- runtime metadata ----------------------------------------------------

    def _write_runtime_files(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "pid": os.getpid(),
            "instance_id": self._instance_id,
            "port": self.port,
            "started_at": time.time(),
            "protocol_version": protocol.PROTOCOL_VERSION,
        }
        self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        self.token_path.write_text(self._token, encoding="utf-8")
        # Best-effort local hardening only: POSIX chmod is not meaningful on
        # Windows ACLs, and this is not a substitute for the token itself.
        try:
            os.chmod(self.token_path, 0o600)
        except OSError:
            pass

    def _cleanup_runtime_files(self) -> None:
        for path in (self.metadata_path, self.token_path):
            try:
                path.unlink()
            except OSError:
                pass

    # -- connection handling ---------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                try:
                    line = await reader.readline()
                except (asyncio.LimitOverrunError, ValueError):
                    await self._send_error(
                        writer, None, "request_too_large", "Request exceeds 64 KB limit"
                    )
                    break
                if not line:
                    break
                if len(line) > protocol.MAX_REQUEST_BYTES:
                    await self._send_error(
                        writer, None, "request_too_large", "Request exceeds 64 KB limit"
                    )
                    break
                await self._handle_request(writer, line)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()

    async def _handle_request(self, writer: asyncio.StreamWriter, line: bytes) -> None:
        try:
            raw = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            await self._send_error(
                writer, None, "malformed_request", "Request body is not valid JSON"
            )
            return
        if not isinstance(raw, dict):
            await self._send_error(
                writer, None, "malformed_request", "Request body must be a JSON object"
            )
            return

        request_id = raw.get("request_id")
        request_id = request_id if isinstance(request_id, str) else None

        token = raw.get("token")
        if not isinstance(token, str) or not hmac.compare_digest(token, self._token):
            await self._send_error(
                writer, request_id, "auth_failed", "Invalid or missing control token"
            )
            return

        action = raw.get("action")
        if not isinstance(action, str):
            await self._send_error(writer, request_id, "malformed_request", "Missing 'action'")
            return
        if action in protocol.FORBIDDEN_ACTIONS:
            await self._send_error(
                writer,
                request_id,
                "forbidden_action",
                f"'{action}' is never permitted over the control protocol",
            )
            return
        if action not in protocol.ALLOWED_ACTIONS:
            await self._send_error(
                writer, request_id, "unknown_action", f"Unknown action: {action}"
            )
            return

        payload = raw.get("payload") or {}
        if not isinstance(payload, dict):
            await self._send_error(
                writer, request_id, "malformed_request", "'payload' must be an object"
            )
            return

        try:
            result = await self._dispatch(action, payload)
        except Exception as exc:  # noqa: BLE001 - every failure must become a clean protocol error
            await self._send_error(writer, request_id, "action_failed", str(exc))
            return
        await self._send_ok(writer, request_id, result)

    async def _dispatch(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        dispatcher = self.dispatcher
        if action == "ping":
            return await dispatcher.ping()
        if action == "status":
            return dispatcher.get_status()
        if action == "wait_ready":
            return dispatcher.wait_ready_status()
        if action == "state":
            return dispatcher.get_state()
        if action == "snapshot":
            return dispatcher.get_snapshot()
        if action == "logs":
            entries = dispatcher.get_logs(
                limit=int(payload.get("limit", 20)),
                subsystem=payload.get("subsystem"),
                severity=payload.get("severity"),
            )
            return {"entries": entries}
        if action == "chat":
            text = payload.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError("payload.text is required")
            session = payload.get("session") or "automation"
            return await dispatcher.chat(str(session), text)
        if action == "command":
            text = payload.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError("payload.text is required")
            session = payload.get("session") or "automation"
            return await dispatcher.command(str(session), text)
        raise ValueError(f"Unhandled action: {action}")

    # -- responses -------------------------------------------------------------

    async def _send_ok(
        self, writer: asyncio.StreamWriter, request_id: str | None, result: dict[str, Any]
    ) -> None:
        response = ControlResponse(request_id=request_id, ok=True, result=result)
        await self._send(writer, response)

    async def _send_error(
        self, writer: asyncio.StreamWriter, request_id: str | None, code: str, message: str
    ) -> None:
        response = ControlResponse(
            request_id=request_id, ok=False, error=ControlError(code=code, message=message)
        )
        await self._send(writer, response)

    async def _send(self, writer: asyncio.StreamWriter, response: ControlResponse) -> None:
        data = (response.model_dump_json() + "\n").encode("utf-8")
        writer.write(data)
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
