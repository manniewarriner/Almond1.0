"""End-to-end tests for the control bridge's real TCP transport.

Two kinds of test live here:

* App-lifecycle tests use Textual's run_test()/Pilot (like
  tests/test_developer_tui.py) to prove the bridge is off by default
  and that enabling it creates/removes the runtime metadata+token
  files with the app's lifecycle.
* Wire-protocol tests run a real ControlServer on a background thread
  with its own event loop -- deliberately decoupled from any Textual
  app/loop -- and drive it with the real synchronous ControlClient
  used by `almond ctl`, over an actual loopback socket.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from dataclasses import replace

import pytest

from almond_ai.app import AlmondDeveloperApp
from almond_ai.config import DeveloperConfig, ModelSettings
from almond_ai.control.client import (
    ControlAuthError,
    ControlClient,
    ControlUnavailableError,
    discover,
)
from almond_ai.control.dispatcher import ApplicationDispatcher
from almond_ai.control.protocol import MAX_REQUEST_BYTES
from almond_ai.control.server import ControlServer


def _fake_config(**kwargs) -> DeveloperConfig:
    return DeveloperConfig(model=ModelSettings(provider="fake"), **kwargs)


# -- app lifecycle -------------------------------------------------------------


def test_bridge_is_disabled_by_default():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config(control_enabled=False))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.control_server is None

    asyncio.run(exercise())


def test_enabling_creates_and_then_removes_runtime_files():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config(control_enabled=True))
        metadata_path = token_path = None
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for _ in range(50):
                if app.control_server is not None and app.control_server.metadata_path.exists():
                    break
                await asyncio.sleep(0.05)
            assert app.control_server is not None
            metadata_path = app.control_server.metadata_path
            token_path = app.control_server.token_path
            assert metadata_path.exists()
            assert token_path.exists()
        for _ in range(50):
            if not metadata_path.exists() and not token_path.exists():
                break
            await asyncio.sleep(0.05)
        assert not metadata_path.exists()
        assert not token_path.exists()

    asyncio.run(exercise())


# -- wire protocol, driven by the real synchronous ControlClient ---------------


class _BackgroundServer:
    """Runs a real, *mounted* AlmondDeveloperApp plus its ControlServer on a
    background thread with its own event loop.

    Deliberately not sharing a loop with the test's own thread, so tests
    here exercise the same synchronous, one-connection-per-call
    ControlClient that `almond ctl` actually uses (which calls
    `asyncio.run`, and so cannot be driven from inside another running
    loop). The app must stay mounted (inside `run_test()`) for the
    whole run, because dispatcher.command()/chat() touch real widgets
    (e.g. `_update_status`) exactly as they would from the real
    `on_mount`-started server.
    """

    def __init__(self, config, runtime_dir) -> None:
        self._config = config
        self._runtime_dir = runtime_dir
        self._ready = threading.Event()
        self._stop_requested = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.app: AlmondDeveloperApp | None = None
        self.server: ControlServer | None = None

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        loop.run_until_complete(self._main())

    async def _main(self) -> None:
        app = AlmondDeveloperApp(self._config)
        self.app = app
        dispatcher = ApplicationDispatcher(app)
        server = ControlServer(dispatcher, self._runtime_dir)
        self.server = server
        async with app.run_test(size=(120, 40)):
            await server.start()
            self._ready.set()
            while not self._stop_requested.is_set():
                await asyncio.sleep(0.05)
            await server.stop()

    def __enter__(self) -> _BackgroundServer:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Background control server did not start in time")
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop_requested.set()
        self._thread.join(timeout=5)


@pytest.fixture
def running_server(tmp_path):
    runtime_dir = tmp_path / "runtime"
    with _BackgroundServer(_fake_config(control_enabled=True), runtime_dir) as background:
        yield background, tmp_path


def test_ping_status_command_and_chat_round_trip(running_server):
    _background, data_dir = running_server
    client = ControlClient(discover(data_dir))

    ping = client.call("ping")
    assert ping.ok
    assert ping.result["pong"] is True

    status = client.call("status")
    assert status.ok
    assert status.result["provider"] == "fake"

    command = client.call("command", {"session": "automation", "text": "/help"})
    assert command.ok
    assert command.result["status"] == "ok"

    chat = client.call("chat", {"session": "automation", "text": "hello"})
    assert chat.ok
    assert "DEV MOCK" in chat.result["text"]


def test_invalid_token_is_rejected(running_server):
    _background, data_dir = running_server
    handle = discover(data_dir)
    bad_handle = replace(handle, token="not-the-real-token")
    with pytest.raises(ControlAuthError):
        ControlClient(bad_handle).call("ping")


def test_stale_token_is_rejected_after_restart(tmp_path):
    # Simulate a restart: the first instance stops (invalidating its
    # token) and a second instance starts in its place -- a caller still
    # holding the old token must be rejected by the new instance.
    runtime_dir = tmp_path / "runtime"
    with _BackgroundServer(_fake_config(control_enabled=True), runtime_dir):
        old_handle = discover(tmp_path)

    with _BackgroundServer(_fake_config(control_enabled=True), runtime_dir):
        new_handle = discover(tmp_path)
        assert new_handle.token != old_handle.token
        # The old token, replayed against the new instance's port, must be
        # rejected -- a restart invalidates every previously issued token.
        stale_handle = replace(old_handle, port=new_handle.port)
        with pytest.raises(ControlAuthError):
            ControlClient(stale_handle).call("ping")
        assert ControlClient(new_handle).call("ping").ok


def _raw_request_line(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


def _envelope(action: str, token: str, payload: dict | None = None) -> dict:
    return {
        "version": 1,
        "request_id": "r",
        "action": action,
        "token": token,
        "payload": payload or {},
    }


def _send_raw(port: int, data: bytes) -> dict:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(data)
        sock.settimeout(5)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk or chunk.endswith(b"\n"):
                chunks.append(chunk)
                break
            chunks.append(chunk)
        line = b"".join(chunks).splitlines()[0]
        return json.loads(line)


def test_forbidden_action_is_rejected_explicitly(running_server):
    _background, data_dir = running_server
    handle = discover(data_dir)
    for action in ("shell", "exec", "python", "eval", "sql", "delete", "process_launch"):
        response = _send_raw(handle.port, _raw_request_line(_envelope(action, handle.token)))
        assert response["ok"] is False
        assert response["error"]["code"] == "forbidden_action"


def test_unknown_action_is_rejected(running_server):
    _background, data_dir = running_server
    handle = discover(data_dir)
    response = _send_raw(
        handle.port, _raw_request_line(_envelope("not_a_real_action", handle.token))
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "unknown_action"


def test_malformed_json_is_handled_safely(running_server):
    _background, data_dir = running_server
    handle = discover(data_dir)
    response = _send_raw(handle.port, b"{not valid json\n")
    assert response["ok"] is False
    assert response["error"]["code"] == "malformed_request"


def test_oversized_request_is_rejected(running_server):
    _background, data_dir = running_server
    handle = discover(data_dir)
    huge_payload = {"text": "x" * (MAX_REQUEST_BYTES + 1)}
    data = _raw_request_line(_envelope("chat", handle.token, huge_payload))
    assert len(data) > MAX_REQUEST_BYTES
    with socket.create_connection(("127.0.0.1", handle.port), timeout=5) as sock:
        sock.sendall(data)
        sock.settimeout(5)
        try:
            reply = sock.recv(4096)
        except (TimeoutError, OSError):
            reply = b""
    if reply:
        response = json.loads(reply.splitlines()[0])
        assert response["ok"] is False
        assert response["error"]["code"] == "request_too_large"


def test_control_disabled_client_reports_unavailable(tmp_path):
    with pytest.raises(ControlUnavailableError):
        discover(tmp_path)
