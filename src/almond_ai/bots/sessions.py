"""Thin session manager layered on top of the existing AgentRegistry/provider.

One `AgentSession` per bot, all sharing the same underlying model
provider (`AlmondDeveloperApp.provider`) -- this module only tracks
which bot is active and keeps each bot's messages/status/pending
confirmation apart. It does not talk to the provider itself; callers
(`AlmondDeveloperApp.run_chat`) still drive the provider directly.
"""

from __future__ import annotations

from almond_ai.bots.models import AgentSession
from almond_ai.bots.registry import GENERAL_BOT_ID


class SessionManager:
    def __init__(self, bots) -> None:
        self.bots: dict[str, object] = {}
        self.sessions: dict[str, AgentSession] = {}
        self._order: list[str] = []
        for bot in bots:
            self.add_bot(bot)
        self.active_id = GENERAL_BOT_ID
        self._ensure_session(GENERAL_BOT_ID)

    def add_bot(self, bot) -> None:
        if bot.id not in self.bots:
            self._order.append(bot.id)
        self.bots[bot.id] = bot

    def my_bots(self) -> list:
        """Bots shown under "My Bots" -- everything except General Chat."""
        return [self.bots[bot_id] for bot_id in self._order if bot_id != GENERAL_BOT_ID]

    def _ensure_session(self, bot_id: str) -> AgentSession:
        if bot_id not in self.sessions:
            bot = self.bots[bot_id]
            self.sessions[bot_id] = AgentSession(id=bot_id, bot_id=bot_id, name=bot.name)
        return self.sessions[bot_id]

    def switch(self, bot_id: str) -> AgentSession:
        if bot_id not in self.bots:
            raise ValueError(f"Unknown bot: {bot_id}")
        session = self._ensure_session(bot_id)
        self.active_id = bot_id
        return session

    def active(self) -> AgentSession:
        return self._ensure_session(self.active_id)

    def get(self, bot_id: str) -> AgentSession:
        if bot_id not in self.bots:
            raise ValueError(f"Unknown bot: {bot_id}")
        return self._ensure_session(bot_id)
