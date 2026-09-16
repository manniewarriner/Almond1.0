"""Left sidebar: General Chat, New Bot, My Bots, Settings.

Replaces the old flat developer-navigation Sidebar. Technical views
(Tools, Data & RAG, Integrations, Evaluation, Logs, Deploy, Permissions)
are no longer listed here -- they stay fully reachable through
Settings > Developer (see `ui.screens.views.SettingsView`), slash
commands, and `almond ctl`.
"""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Label, Static

from almond_ai.ui.widgets.sidebar import NavItem


class NewBotItem(Label):
    """Sidebar entry that opens the bot-creation flow."""

    class Requested(Message):
        pass

    def __init__(self) -> None:
        super().__init__("+ New Bot", id="nav-new-bot", classes="nav-item new-bot-item")

    def on_click(self) -> None:
        self.post_message(self.Requested())


class BotNavItem(Static):
    """One bot row: icon, name, and a subtle status label once it isn't idle."""

    class Selected(Message):
        def __init__(self, bot_id: str) -> None:
            self.bot_id = bot_id
            super().__init__()

    def __init__(self, bot) -> None:
        self.bot = bot
        self._status = "idle"
        super().__init__(self._label(), id=f"bot-{bot.id}", classes="nav-item bot-nav-item")

    def _label(self) -> str:
        if self._status != "idle":
            # Transient runtime activity (thinking/working/...) always wins
            # over the bot's static capability badge.
            suffix = f"  [#9CA3A8]{escape(self._status)}[/]"
        elif self.bot.status in ("wip", "experimental"):
            # No live activity -- fall back to the bot's baseline capability
            # maturity (Research/Coding are always WIP/Experimental today).
            suffix = f"  [#9CA3A8]{escape(self.bot.status.upper())}[/]"
        else:
            suffix = ""
        return f"[{self.bot.accent}]{self.bot.icon}[/] {escape(self.bot.name)}{suffix}"

    def set_status(self, status: str) -> None:
        self._status = status
        self.update(self._label())

    def on_click(self) -> None:
        self.post_message(self.Selected(self.bot.id))


class BotSidebar(Static):
    """Narrow, fixed left sidebar for the simplified assistant UI."""

    def __init__(self, general_bot, my_bots) -> None:
        super().__init__(id="navigation")
        self.general_bot = general_bot
        self.my_bots = my_bots

    def compose(self) -> ComposeResult:
        yield Static("[b]Almond AI[/]", id="sidebar-brand")
        yield BotNavItem(self.general_bot)
        yield NewBotItem()
        yield Label("MY BOTS", id="sidebar-bots-label")
        with VerticalScroll(id="bot-list"):
            for bot in self.my_bots:
                yield BotNavItem(bot)
        yield NavItem("Settings").add_class("sidebar-settings-item")

    def add_bot_item(self, bot) -> None:
        self.query_one("#bot-list", VerticalScroll).mount(BotNavItem(bot))

    def set_active_bot(self, bot_id: str | None) -> None:
        for item in self.query(BotNavItem):
            item.set_class(item.bot.id == bot_id, "nav-selected")
        for item in self.query(NavItem):
            item.remove_class("nav-selected")

    def set_active_settings(self) -> None:
        for item in self.query(BotNavItem):
            item.remove_class("nav-selected")
        self.query_one("#nav-settings", NavItem).add_class("nav-selected")
