"""Reusable presentation widgets for the developer console."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static


class SectionHeader(Label):
    """Quiet, consistent section heading."""

    def __init__(self, title: str) -> None:
        super().__init__(title, classes="section-title")


class Card(Vertical):
    """Bordered content group with comfortable internal spacing."""

    def __init__(self, title: str, *children, id: str | None = None, classes: str = "") -> None:
        super().__init__(id=id, classes=f"card {classes}".strip())
        self.card_title = title
        self.card_children = children

    def compose(self) -> ComposeResult:
        yield SectionHeader(self.card_title)
        yield from self.card_children


class StatusIndicator(Static):
    """Small status label using restrained semantic colour."""

    def __init__(self, label: str, status: str = "online", **kwargs) -> None:
        tone = "#6F9B74" if status == "online" else "#9CA3A8"
        super().__init__(f"[{tone}]●[/] {label}", markup=True, **kwargs)


class QuickCommand(Static):
    """Command and description pair."""

    def __init__(self, command: str, description: str) -> None:
        super().__init__(
            f"[#F15A24]{command:<13}[/][#9CA3A8]{description}[/]",
            markup=True,
            classes="quick-command",
        )


class AgentStatus(Static):
    """Compact agent availability row."""

    def __init__(self, name: str, description: str) -> None:
        super().__init__(
            f"[#6F9B74]●[/] [b]{name:<11}[/][#9CA3A8]{description}[/]",
            markup=True,
            classes="agent-status",
        )
