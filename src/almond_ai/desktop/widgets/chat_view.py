"""Generic chat surface shared by General Chat, Research, Drafting, and Document.

Each bot gets its own ChatView instance (own history layout, own empty
state copy) but they're all the same widget class -- there is exactly one
implementation of "render messages, stream a reply, take composer input,"
not one per bot.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from almond_ai.desktop import theme
from almond_ai.desktop.icons import nut_pixmap
from almond_ai.desktop.widgets.composer import Composer


class _ThinkingIndicator(QWidget):
    """Shown in place of the reply text until the first token arrives.

    A static bot mark plus three dots that light up in sequence, shared by
    every bot (General/Research/Drafting/Document) since they all use this
    same ChatView. Deliberately cheap to render: a single QTimer driving
    plain stylesheet colour changes on three QLabels, no QGraphicsEffect
    (which forces an offscreen alpha-blended buffer every frame) and no
    QPropertyAnimation (which repaints continuously at ~60Hz for the
    duration of each pulse). A style ticking every 350ms is indistinguishable
    "working" motion for this purpose at a fraction of the GPU/CPU cost.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        icon = QLabel()
        icon.setPixmap(nut_pixmap("almond", theme.ACCENT, size=14))
        layout.addWidget(icon)

        self._dots = [QLabel("●") for _ in range(3)]
        for dot in self._dots:
            layout.addWidget(dot)
        layout.addStretch(1)

        self._phase = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_timer.start(350)
        self._tick_dots()

    def _tick_dots(self) -> None:
        for i, dot in enumerate(self._dots):
            color = theme.ACCENT if i == self._phase % 3 else theme.TEXT_MUTED
            dot.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 700;")
        self._phase += 1

    def stop(self) -> None:
        self._dot_timer.stop()


class ChatView(QWidget):
    message_submitted = Signal(str)
    primary_action_clicked = Signal()
    secondary_action_clicked = Signal()
    regenerate_requested = Signal()

    def __init__(
        self,
        *,
        empty_title: str = "",
        empty_body: str = "",
        empty_status: str | None = None,
        action_label: str | None = None,
        secondary_label: str | None = None,
        empty_widget: QWidget | None = None,
        show_composer: bool = True,
        composer_placeholder: str = "Message Almond…",
        toolbar: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self._stack = QStackedWidget()
        self._empty_page = (
            empty_widget
            if empty_widget is not None
            else self._build_empty_state(
                empty_title, empty_body, empty_status, action_label, secondary_label
            )
        )
        self._history_page, self._messages_layout = self._build_history()
        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._history_page)
        outer.addWidget(self._stack, 1)

        # Pinned above the composer, visible in both the empty and history
        # states -- unlike the empty-state's own action button(s), which
        # disappear once the first message is sent.
        if toolbar is not None:
            outer.addWidget(toolbar)

        self.composer: Composer | None = None
        if show_composer:
            self.composer = Composer(composer_placeholder)
            self.composer.message_submitted.connect(self.message_submitted)
            outer.addWidget(self.composer)

        self._pending_bubble: QLabel | None = None
        self._pending_thinking: _ThinkingIndicator | None = None
        self._pending_timing_label: QLabel | None = None
        self._primary_action_button: QPushButton | None = None
        self._secondary_action_button: QPushButton | None = None

    # -- empty state -----------------------------------------------------

    def _build_empty_state(
        self,
        title: str,
        body: str,
        status: str | None,
        action_label: str | None,
        secondary_label: str | None,
    ) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addStretch(1)
        title_label = QLabel(title)
        title_label.setObjectName("emptyTitle")
        title_row.addWidget(title_label)
        if status:
            badge = QLabel(status)
            badge.setObjectName("comingSoonBadge")
            title_row.addWidget(badge)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        body_label = QLabel(body)
        body_label.setObjectName("emptyBody")
        body_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body_label.setWordWrap(True)
        body_label.setMaximumWidth(440)
        layout.addSpacing(6)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(body_label)
        row.addStretch(1)
        layout.addLayout(row)

        if action_label or secondary_label:
            layout.addSpacing(18)
            buttons = QHBoxLayout()
            buttons.addStretch(1)
            if action_label:
                primary = QPushButton(action_label)
                primary.setObjectName("primaryAction")
                primary.setCursor(Qt.CursorShape.PointingHandCursor)
                primary.clicked.connect(self.primary_action_clicked)
                buttons.addWidget(primary)
                self._primary_action_button = primary
            if secondary_label:
                secondary = QPushButton(secondary_label)
                secondary.setObjectName("secondaryAction")
                secondary.setCursor(Qt.CursorShape.PointingHandCursor)
                secondary.clicked.connect(self.secondary_action_clicked)
                buttons.addWidget(secondary)
                self._secondary_action_button = secondary
            buttons.addStretch(1)
            layout.addLayout(buttons)

        layout.addStretch(3)
        return page

    def set_primary_action_label(self, text: str) -> None:
        if self._primary_action_button is not None:
            self._primary_action_button.setText(text)

    def set_secondary_action_label(self, text: str) -> None:
        if self._secondary_action_button is not None:
            self._secondary_action_button.setText(text)

    # -- history -----------------------------------------------------------

    def _build_history(self) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setObjectName("chatScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(14)
        layout.addStretch(1)
        scroll.setWidget(container)
        self._scroll_area = scroll
        return scroll, layout

    def show_empty_state(self, empty: bool) -> None:
        self._stack.setCurrentWidget(self._empty_page if empty else self._history_page)

    # -- rendering ---------------------------------------------------------

    def clear_history(self) -> None:
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._pending_bubble = None
        self._pending_thinking = None
        self._pending_timing_label = None

    def render_messages(self, messages: list[dict[str, str]]) -> None:
        self.clear_history()
        for message in messages:
            if message["role"] == "user":
                self.add_user_message(message["content"])
            elif message["role"] == "assistant":
                self.add_assistant_message(message["content"])
        self.show_empty_state(not messages)

    def add_user_message(self, text: str) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        bubble = QLabel(text)
        bubble.setTextFormat(Qt.TextFormat.PlainText)
        bubble.setObjectName("userBubble")
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(480)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(bubble)
        self._insert_row(row)

    def begin_assistant_message(self, *, show_thinking: bool = True) -> None:
        """Add an empty, borderless assistant row that streaming updates in place.

        `show_thinking` starts a breathing-bot/colour-cycling-dots indicator
        in place of the (still-empty) reply text, until the first non-empty
        `update_streaming_text` call swaps it out. Pass False for callers
        that set a fixed status string immediately (e.g. "Preparing
        document…") rather than an actual model reply.
        """
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        label = QLabel("Almond")
        label.setObjectName("assistantLabel")
        layout.addWidget(label)

        thinking: _ThinkingIndicator | None = None
        if show_thinking:
            thinking = _ThinkingIndicator()
            layout.addWidget(thinking)

        text = QLabel("")
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setObjectName("assistantText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setVisible(not show_thinking)
        layout.addWidget(text)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        copy_button = QPushButton("Copy")
        copy_button.setObjectName("secondaryAction")
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_button.clicked.connect(lambda: self._copy_text(text.text()))
        actions.addWidget(copy_button)

        regenerate_button = QPushButton("Regenerate")
        regenerate_button.setObjectName("secondaryAction")
        regenerate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        regenerate_button.clicked.connect(self.regenerate_requested)
        actions.addWidget(regenerate_button)

        timing_label = QLabel("")
        timing_label.setObjectName("timingLabel")
        timing_label.setVisible(False)
        actions.addWidget(timing_label)

        actions.addStretch(1)
        layout.addLayout(actions)

        self._insert_row(row)
        self._pending_bubble = text
        self._pending_thinking = thinking
        self._pending_timing_label = timing_label

    def update_streaming_text(self, text: str) -> None:
        if self._pending_bubble is None:
            return
        if text and self._pending_thinking is not None and not self._pending_thinking.isHidden():
            self._pending_thinking.stop()
            self._pending_thinking.setVisible(False)
            self._pending_bubble.setVisible(True)
        self._pending_bubble.setText(text)
        self._scroll_to_bottom()

    def set_timing(self, thinking_seconds: float, total_seconds: float) -> None:
        if self._pending_timing_label is None:
            return
        self._pending_timing_label.setText(
            f"Thought for {thinking_seconds:.1f}s · replied in {total_seconds:.1f}s"
        )
        self._pending_timing_label.setVisible(True)

    def add_assistant_message(self, text: str) -> None:
        self.begin_assistant_message(show_thinking=False)
        self.update_streaming_text(text.strip())
        self._pending_bubble = None
        self._pending_thinking = None
        self._pending_timing_label = None

    def _insert_row(self, row: QWidget) -> None:
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, row)
        self.show_empty_state(False)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    @staticmethod
    def _copy_text(text: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)

    def set_busy(self, busy: bool) -> None:
        if self.composer is not None:
            self.composer.set_busy(busy)
