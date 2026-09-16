"""Local JSON persistence for user-created bots.

Mirrors the project's existing pattern of small local JSON files under
the app data folder (see `data/users.json`) rather than adding a
database dependency.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from almond_ai.bots.models import BotDefinition


def slugify(name: str, *, taken: frozenset[str] = frozenset()) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "bot"
    if base not in taken:
        return base
    index = 2
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


def load_user_bots(path: Path) -> list[BotDefinition]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = raw.get("bots", []) if isinstance(raw, dict) else raw
    bots = []
    for entry in entries:
        try:
            bots.append(BotDefinition.from_dict(entry))
        except (KeyError, TypeError):
            continue
    return bots


def save_user_bots(path: Path, bots: list[BotDefinition]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"bots": [bot.to_dict() for bot in bots]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
