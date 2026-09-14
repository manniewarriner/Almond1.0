"""Tests for app.security.permissions: fail-closed local permission resolution."""

from __future__ import annotations

import json

import pytest

from app.documents.retrieval import REQUIRED_PERMISSION
from app.errors import ConfigError
from app.security.permissions import load_users, resolve_requester


def test_load_users_missing_file(tmp_path):
    assert load_users(tmp_path / "missing.json") == {}


def test_load_users_valid_file(tmp_path):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps({"users": [{"user_id": "alice", "permissions": ["documents:read"]}]}),
        encoding="utf-8",
    )

    users = load_users(users_file)

    assert users["alice"].permissions == ["documents:read"]


def test_load_users_invalid_json_raises(tmp_path):
    users_file = tmp_path / "users.json"
    users_file.write_text("not json", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_users(users_file)


def test_resolve_requester_known_user(tmp_path):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps({"users": [{"user_id": "alice", "permissions": [REQUIRED_PERMISSION]}]}),
        encoding="utf-8",
    )

    requester = resolve_requester(users_file, "alice")

    assert REQUIRED_PERMISSION in requester.permissions


def test_resolve_requester_unknown_user_fails_closed(tmp_path):
    users_file = tmp_path / "users.json"
    users_file.write_text(json.dumps({"users": []}), encoding="utf-8")

    requester = resolve_requester(users_file, "mallory")

    assert requester.permissions == frozenset()


def test_resolve_requester_missing_file_fails_closed(tmp_path):
    requester = resolve_requester(tmp_path / "does-not-exist.json", "anyone")

    assert requester.permissions == frozenset()
