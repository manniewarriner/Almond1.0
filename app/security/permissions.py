"""Local permission store: maps a user id to a set of granted permissions.

Fails closed: an unknown user id gets zero permissions, never a default
grant. This is deliberately a simple JSON file, not a full RBAC system,
but it is the one seam every access-control decision in the CLI goes
through -- no command builds a Requester by hand anymore.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from app.documents.retrieval import Requester
from app.errors import ConfigError


class UserRecord(BaseModel):
    user_id: str
    permissions: list[str] = []


def load_users(users_file: Path) -> dict[str, UserRecord]:
    if not users_file.is_file():
        return {}
    try:
        raw = json.loads(users_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid users file {users_file}: {exc}") from exc

    users: dict[str, UserRecord] = {}
    for entry in raw.get("users", []):
        record = UserRecord.model_validate(entry)
        users[record.user_id] = record
    return users


def resolve_requester(users_file: Path, user_id: str) -> Requester:
    """Resolve a Requester for user_id. Fails closed: unknown users get no permissions."""
    users = load_users(users_file)
    record = users.get(user_id)
    permissions = frozenset(record.permissions) if record else frozenset()
    return Requester(user_id=user_id, permissions=permissions)
