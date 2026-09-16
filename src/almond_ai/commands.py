"""Slash-command parsing and completion."""

from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: tuple[str, ...]


COMMANDS = (
    "/help",
    "/ask",
    "/search",
    "/calc",
    "/summarise",
    "/draft",
    "/analyse",
    "/rag status",
    "/rag search",
    "/rag inspect",
    "/rag reindex",
    "/rag add",
    "/rag remove",
    "/agent list",
    "/agent use",
    "/agent status",
    "/tools",
    "/permissions",
    "/tool inspect",
    "/tool run",
    "/tool enable",
    "/tool disable",
    "/pdf help",
    "/pdf status",
    "/pdf create",
    "/integrations",
    "/integration inspect",
    "/integration test",
    "/eval list",
    "/eval run",
    "/eval results",
    "/eval compare",
    "/logs",
    "/deploy status",
    "/deploy staging",
    "/deploy production",
    "/rollback",
    "/config",
    "/clear",
    "/exit",
)


def parse_command(text: str) -> ParsedCommand | None:
    value = text.strip()
    if not value.startswith("/"):
        return None
    try:
        parts = shlex.split(value)
    except ValueError as exc:
        raise ValueError("Invalid quoting in command") from exc
    if not parts:
        return None
    return ParsedCommand(parts[0][1:].lower(), tuple(parts[1:]))


def command_suggestions(prefix: str) -> list[str]:
    value = prefix.strip().lower()
    return [command for command in COMMANDS if command.startswith(value)][:10]
