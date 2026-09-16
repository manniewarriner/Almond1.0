"""Data model for bots and their independent chat sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Subtle sidebar status labels. "idle" is the resting state a session
# starts in and returns to; the others are set by SessionManager as a
# session's chat request moves through its lifecycle.
STATUS_IDLE = "idle"
STATUS_THINKING = "thinking"
STATUS_WORKING = "working"
STATUS_WAITING = "waiting"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"

VALID_STATUSES = frozenset(
    {STATUS_IDLE, STATUS_THINKING, STATUS_WORKING, STATUS_WAITING, STATUS_COMPLETE, STATUS_ERROR}
)


@dataclass
class BotDefinition:
    """A named persona layered onto the shared local model.

    `tools` and `rag_enabled` are descriptive metadata surfaced in the UI
    (and available for a future per-bot capability gate) -- this first
    pass does not yet restrict which tools a bot may call beyond the
    existing global permission system in `almond_ai.tools.registry`.
    """

    id: str
    name: str
    description: str
    instructions: str
    tools: list[str] = field(default_factory=list)
    rag_enabled: bool = False
    icon: str = "●"
    accent: str = "#F15A24"
    built_in: bool = False
    # Capability maturity badge ("available" / "wip" / "experimental") --
    # distinct from AgentSession.status, which is per-session runtime state
    # (idle/thinking/working/...). A bot's `status` doesn't change at
    # runtime; it describes whether its `unique_tool` actually does
    # anything yet.
    status: str = "available"
    # The one signature capability this bot is built around (see the Tools
    # view's "Specialist Capabilities" section). None for General Chat and
    # for user-created bots, which don't get a dedicated tool in this pass.
    unique_tool: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "tools": list(self.tools),
            "rag_enabled": self.rag_enabled,
            "icon": self.icon,
            "accent": self.accent,
            "built_in": self.built_in,
            "status": self.status,
            "unique_tool": self.unique_tool,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BotDefinition:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            tools=list(data.get("tools", [])),
            rag_enabled=bool(data.get("rag_enabled", False)),
            icon=data.get("icon", "●"),
            accent=data.get("accent", "#F15A24"),
            built_in=bool(data.get("built_in", False)),
            status=data.get("status", "available"),
            unique_tool=data.get("unique_tool"),
        )


@dataclass
class AgentSession:
    """One bot's independent conversation -- its own history and write-confirmation state."""

    id: str
    bot_id: str
    name: str
    messages: list[dict[str, str]] = field(default_factory=list)
    status: str = STATUS_IDLE
    pending_confirmation: tuple[str, str] | None = None
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.updated_at = time.monotonic()
