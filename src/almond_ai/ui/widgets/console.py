"""Chat console and command-entry widgets."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, RichLog, Static, TextArea


class ConsoleOutput(RichLog):
    """Output stays isolated from navigation and system information."""

    def __init__(self) -> None:
        super().__init__(id="console", markup=True, wrap=True, highlight=False)


class ComposerTextArea(TextArea):
    """Enter submits; Ctrl+J inserts a newline.

    Modifier+Enter combinations (Ctrl+Enter, Shift+Enter, ...) are not sent
    as distinct key events by most terminals -- they arrive identical to
    plain Enter, so a terminal-level "Ctrl+Enter to submit" binding can
    never fire reliably. Ctrl+J (linefeed) is a real, distinct byte every
    terminal transmits correctly, so it is used for newlines instead.
    """

    class Submitted(Message):
        """Posted when the user presses Enter to submit the composer text."""

    async def _on_key(self, event: events.Key) -> None:
        if not self.read_only and event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted())
            return
        if not self.read_only and event.key == "ctrl+j":
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)
            return
        await super()._on_key(event)


class CommandInput(Vertical):
    """Visually distinct multiline command composer."""

    def compose(self) -> ComposeResult:
        yield Static(id="suggestions")
        yield Label("> Message Almond…", id="input-label")
        yield ComposerTextArea(id="composer", soft_wrap=True, tab_behavior="focus")
        yield Static(id="stream-indicator", markup=True)
        yield Label(
            "Enter to submit · Ctrl+J for newline · Ctrl+O to browse for a file",
            id="input-hint",
            classes="secondary",
        )
