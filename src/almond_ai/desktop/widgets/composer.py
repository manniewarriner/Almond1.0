"""Multiline composer: text box + round send button, Enter-to-send."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget


class _ComposerInput(QTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class Composer(QWidget):
    message_submitted = Signal(str)

    def __init__(self, placeholder: str = "Message Almond…", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("composer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(12)

        self._input = _ComposerInput()
        self._input.setObjectName("composerInput")
        self._input.setPlaceholderText(placeholder)
        self._input.setFixedHeight(52)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input.submitted.connect(self._submit)
        layout.addWidget(self._input, 1)

        hint = QLabel("Enter to send · Shift + Enter for a new line")
        hint.setObjectName("composerHint")
        layout.addWidget(hint)

        self._send_button = QPushButton("↑")
        self._send_button.setObjectName("sendButton")
        self._send_button.clicked.connect(self._submit)
        layout.addWidget(self._send_button)

    def _submit(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or not self._send_button.isEnabled():
            return
        self._input.clear()
        self.message_submitted.emit(text)

    def set_busy(self, busy: bool) -> None:
        self._send_button.setEnabled(not busy)
        self._input.setEnabled(not busy)

    def set_text(self, text: str) -> None:
        self._input.setPlainText(text)
        self._input.setFocus()

    def focus(self) -> None:
        self._input.setFocus()
