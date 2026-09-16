"""Left navigation: General Chat, staff specialist bots, Settings.

Deliberately does not surface anything developer-facing (no Agents,
Tools, Data & RAG, Integrations, Evaluation, Logs, Deploy nav items --
those stay terminal-only).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from almond_ai.bots.models import BotDefinition
from almond_ai.desktop import theme
from almond_ai.desktop.icons import bot_icon, brand_mark_pixmap, nut_pixmap

SETTINGS_ID = "__settings__"


class _NavRow(QPushButton):
    """A clickable sidebar row with custom (icon + text) content.

    QPushButton rather than a plain frame so hover/pressed QSS states and
    keyboard/click activation come for free; its own text/icon are left
    unset and a child layout supplies the visible content instead.
    """

    def __init__(self, nav_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.nav_id = nav_id
        self.setObjectName("navItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)


class Sidebar(QWidget):
    item_selected = Signal(str)  # bot id, "general", or SETTINGS_ID

    def __init__(self, staff_bots: list[BotDefinition], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(292)
        self._rows: dict[str, _NavRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 22, 18, 18)
        outer.setSpacing(4)

        outer.addWidget(self._build_brand_block())
        outer.addSpacing(18)

        outer.addWidget(self._build_general_row())

        section = QLabel("My bots")
        section.setObjectName("sectionLabel")
        outer.addWidget(section)

        for bot in staff_bots:
            outer.addWidget(self._build_bot_row(bot))

        outer.addStretch(1)
        outer.addWidget(self._build_settings_row())

    def _build_brand_block(self) -> QWidget:
        block = QWidget()
        layout = QHBoxLayout(block)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(14)

        mark = QLabel()
        mark.setPixmap(brand_mark_pixmap(theme.ACCENT, 46))
        mark.setFixedSize(46, 46)
        layout.addWidget(mark)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = QLabel("Almond AI")
        title.setObjectName("brand")
        text_col.addWidget(title)
        subtitle = QLabel("Your financial assistant")
        subtitle.setObjectName("brandSubtitle")
        text_col.addWidget(subtitle)
        layout.addLayout(text_col)
        layout.addStretch(1)
        return block

    # -- row builders -----------------------------------------------------

    def _build_general_row(self) -> QWidget:
        row = _NavRow("general")
        row.setMinimumHeight(68)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(nut_pixmap("general", theme.BOT_ACCENTS["general"], 28))
        icon_label.setFixedSize(28, 28)
        layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel("General Chat")
        name.setObjectName("navRowTitle")
        name.setStyleSheet("font-weight: 700;")
        text_col.addWidget(name)

        subtitle_row = QHBoxLayout()
        subtitle_row.setSpacing(8)
        subtitle = QLabel("Your financial assistant")
        subtitle.setObjectName("navSubtitle")
        subtitle_row.addWidget(subtitle)
        badge = QLabel("Coming Soon")
        badge.setObjectName("comingSoonBadge")
        subtitle_row.addWidget(badge)
        subtitle_row.addStretch(1)
        text_col.addLayout(subtitle_row)

        layout.addLayout(text_col, 1)
        row.clicked.connect(lambda: self.item_selected.emit(row.nav_id))
        self._rows[row.nav_id] = row
        return row

    def _build_bot_row(self, bot: BotDefinition) -> QWidget:
        row = _NavRow(bot.id)
        row.setMinimumHeight(68)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(14)

        icon_label = QLabel()
        icon = bot_icon(bot.id, theme.BOT_ACCENTS.get(bot.id, theme.ACCENT), size=28)
        if icon is not None:
            icon_label.setPixmap(icon.pixmap(28, 28))
        icon_label.setFixedSize(28, 28)
        layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(bot.name)
        name.setObjectName("navRowTitle")
        text_col.addWidget(name)

        subtitle_row = QHBoxLayout()
        subtitle_row.setSpacing(8)
        subtitle = QLabel(bot.description)
        subtitle.setObjectName("navSubtitle")
        subtitle_row.addWidget(subtitle)
        if bot.status == "wip":
            badge = QLabel("Coming Soon")
            badge.setObjectName("comingSoonBadge")
            subtitle_row.addWidget(badge)
        subtitle_row.addStretch(1)
        text_col.addLayout(subtitle_row)

        layout.addLayout(text_col, 1)
        row.clicked.connect(lambda: self.item_selected.emit(row.nav_id))
        self._rows[row.nav_id] = row
        return row

    def _build_settings_row(self) -> QWidget:
        row = _NavRow(SETTINGS_ID)
        row.setMinimumHeight(44)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(10)
        label = QLabel("Settings")
        label.setObjectName("sidebarFooterLabel")
        layout.addWidget(label)
        layout.addStretch(1)
        row.clicked.connect(lambda: self.item_selected.emit(row.nav_id))
        self._rows[row.nav_id] = row
        return row

    # -- active state -------------------------------------------------------

    def set_active(self, nav_id: str) -> None:
        for row_id, row in self._rows.items():
            row.setProperty("active", row_id == nav_id)
            row.style().unpolish(row)
            row.style().polish(row)
