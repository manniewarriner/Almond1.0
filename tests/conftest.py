"""Shared test fixtures: isolate each test from the real cwd/.env and OS env vars."""

from __future__ import annotations

import json
import os

import pytest


async def wait_until_ready(app, pilot, timeout: float = 15.0) -> None:
    """Poll `app.ready` directly instead of `app.workers.wait_for_complete()`.

    `LoadingScreen.on_mount()` registers its `_boot()` worker asynchronously;
    under system load there's a real race where `wait_for_complete()` can
    return before that worker has even started, letting a test proceed
    before the (real, ~2.5s minimum) loading screen has actually dismissed.
    Polling `app.ready` with `pilot.pause()` between checks waits for the
    actual condition tests care about, not a worker-registration heuristic.
    """
    import time

    deadline = time.monotonic() + timeout
    while not app.ready:
        if time.monotonic() > deadline:
            raise AssertionError(f"app did not become ready within {timeout}s")
        await pilot.pause()


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("FIRM_AI_"):
            monkeypatch.delenv(key, raising=False)

    # Default permission fixture: CLI commands run as --user local, so grant
    # it here unless a test overrides FIRM_AI_USERS_FILE to test the
    # fail-closed (unknown user) path explicitly.
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps({"users": [{"user_id": "local", "permissions": ["documents:read"]}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRM_AI_USERS_FILE", str(users_file))

    return tmp_path
