"""Shared test fixtures: isolate each test from the real cwd/.env and OS env vars."""

from __future__ import annotations

import json
import os

import pytest


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
