"""Guided composer for the Drafting bot's one action: Draft Client Email.

Purely a prompt builder -- it produces a structured instruction that gets
sent through the normal chat path (same as every other message), and the
model drafts text only. Nothing here sends, schedules, or delivers
anything.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)


class DraftingDialog(QDialog):
    def __init__(self, parent=None, initial: dict[str, str] | None = None) -> None:
        super().__init__(parent)
        is_edit = initial is not None
        self.setWindowTitle("Edit Draft" if is_edit else "Draft Client Email")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Drafts the email text. Almond never sends, schedules, or delivers it.\n"
            "Review before use — the draft may state things as confirmed/complete that "
            "weren't in what you gave it."
        )
        intro.setObjectName("dialogIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        initial = initial or {}
        self.purpose = self._field(layout, "Purpose", required=True)
        self.client_context = self._field(layout, "Client / context")
        self.key_points = self._field(layout, "Key points", multiline=True)
        self.tone = self._field(layout, "Tone (optional)")
        self.purpose.setText(initial.get("purpose", ""))
        self.client_context.setText(initial.get("client_context", ""))
        self.key_points.setPlainText(initial.get("key_points", ""))
        self.tone.setText(initial.get("tone", ""))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Redraft" if is_edit else "Draft Email"
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.purpose.textChanged.connect(self._update_ok_enabled)
        self._update_ok_enabled()

    def _field(
        self,
        layout: QVBoxLayout,
        label_text: str,
        *,
        required: bool = False,
        multiline: bool = False,
    ):
        label = QLabel(label_text + (" *" if required else ""))
        label.setObjectName("fieldLabel")
        layout.addWidget(label)
        field = QTextEdit() if multiline else QLineEdit()
        if multiline:
            field.setFixedHeight(70)
        layout.addWidget(field)
        return field

    def _update_ok_enabled(self) -> None:
        self._ok_button.setEnabled(bool(self.purpose.text().strip()))

    def _on_accept(self) -> None:
        if not self.purpose.text().strip():
            return
        self.accept()

    def _text_of(self, field) -> str:
        return field.toPlainText().strip() if isinstance(field, QTextEdit) else field.text().strip()

    def fields(self) -> dict[str, str]:
        """Raw field values, suitable for re-opening this dialog pre-filled later."""
        return {
            "purpose": self._text_of(self.purpose),
            "client_context": self._text_of(self.client_context),
            "key_points": self._text_of(self.key_points),
            "tone": self._text_of(self.tone),
        }

    def build_prompt(self) -> str:
        """Structured instruction the Drafting bot's system prompt is built to expect."""
        fields = self.fields()
        lines = ["Draft a client email.", f"Purpose: {fields['purpose']}"]
        if fields["client_context"]:
            lines.append(f"Client context: {fields['client_context']}")
        if fields["tone"]:
            lines.append(f"Tone: {fields['tone']}")
        if fields["key_points"]:
            lines.append(f"Key points: {fields['key_points']}")
        return "\n".join(lines)

    @staticmethod
    def get_prompt(parent=None, initial: dict[str, str] | None = None) -> tuple[str, dict[str, str]] | None:
        """Show the dialog (pre-filled with `initial` if given).

        Returns `(prompt, fields)` on accept -- `fields` is the raw field
        dict, kept by the caller so a later "Edit" can re-open this dialog
        pre-filled with exactly what was submitted this time.
        """
        dialog = DraftingDialog(parent, initial=initial)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.build_prompt(), dialog.fields()
        return None
