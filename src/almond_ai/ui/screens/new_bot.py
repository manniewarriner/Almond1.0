"""Simple in-terminal bot-creation flow, opened from the "+ New Bot" sidebar item."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Select, Static, TextArea

from almond_ai.bots.models import BotDefinition
from almond_ai.bots.storage import slugify

ICON_OPTIONS = [
    ("● circle", "●"),
    ("◆ diamond", "◆"),
    ("■ square", "■"),
    ("▲ triangle", "▲"),
    ("☁ cloud", "☁"),
    ("◉ ring", "◉"),
    ("▣ block", "▣"),
    ("◈ gem", "◈"),
]

ACCENT_OPTIONS = [
    ("Orange", "#F15A24"),
    ("Purple", "#9B7ED8"),
    ("Green", "#6F9B74"),
    ("Blue", "#6E9BC7"),
    ("Pink", "#D889A8"),
    ("Amber", "#B58A52"),
]

# A user-created bot may only pick from this fixed, read-only allowlist --
# never a free-text tool name. Real execution is still gated by
# ToolRegistry.authorize_run regardless of what a bot lists here, but this
# keeps the UI itself from ever suggesting a bot could grant itself shell,
# SQL, file-write, email-send, trading, or network access.
SAFE_TOOL_ALLOWLIST = ("document_search", "calculator")


class NewBotScreen(ModalScreen[BotDefinition | None]):
    """Asks for name, description, instructions, and a few optional extras."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, existing_ids: frozenset[str]) -> None:
        super().__init__()
        self.existing_ids = existing_ids

    def compose(self) -> ComposeResult:
        with Vertical(id="new-bot-dialog"):
            yield Static("New Bot", id="new-bot-title")
            yield Static("Bot name", classes="new-bot-label")
            yield Input(placeholder="e.g. Portfolio Analyst", id="bot-name")
            yield Static("Description", classes="new-bot-label")
            yield Input(placeholder="One line, shown under the bot's name", id="bot-description")
            yield Static("Instructions / role", classes="new-bot-label")
            yield TextArea(id="bot-instructions", soft_wrap=True)
            yield Static("Tools (optional, allow-listed only)", classes="new-bot-label")
            with Horizontal(id="new-bot-tools"):
                for tool_name in SAFE_TOOL_ALLOWLIST:
                    yield Checkbox(tool_name, id=f"bot-tool-{tool_name}")
            yield Checkbox("RAG access", id="bot-rag")
            with Horizontal(id="new-bot-selects"):
                yield Select(ICON_OPTIONS, value="●", id="bot-icon", allow_blank=False)
                yield Select(ACCENT_OPTIONS, value="#F15A24", id="bot-accent", allow_blank=False)
            yield Static("", id="new-bot-error")
            with Horizontal(id="new-bot-actions"):
                yield Button("Cancel", id="cancel-bot-btn")
                yield Button("Create", id="create-bot-btn", variant="primary")

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel-bot-btn")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#create-bot-btn")
    def create(self) -> None:
        name = self.query_one("#bot-name", Input).value.strip()
        if not name:
            self.query_one("#new-bot-error", Static).update("[#A96363]Bot name is required.[/]")
            return
        description = self.query_one("#bot-description", Input).value.strip()
        instructions = self.query_one("#bot-instructions", TextArea).text.strip()
        tools = [
            tool_name
            for tool_name in SAFE_TOOL_ALLOWLIST
            if self.query_one(f"#bot-tool-{tool_name}", Checkbox).value
        ]
        rag_enabled = self.query_one("#bot-rag", Checkbox).value
        icon = self.query_one("#bot-icon", Select).value
        accent = self.query_one("#bot-accent", Select).value
        bot = BotDefinition(
            id=slugify(name, taken=self.existing_ids),
            name=name,
            description=description,
            instructions=instructions,
            tools=tools,
            rag_enabled=rag_enabled,
            icon=str(icon),
            accent=str(accent),
            built_in=False,
        )
        self.dismiss(bot)
