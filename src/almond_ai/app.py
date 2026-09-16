"""Premium full-screen Textual developer console."""

from __future__ import annotations

import asyncio
import json
import re
import time
from decimal import Decimal
from pathlib import Path

from rich.markup import escape
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ProgressBar, RichLog, Static, TextArea

from almond_ai import __version__
from almond_ai.bots.models import STATUS_COMPLETE, STATUS_ERROR, STATUS_THINKING, BotDefinition
from almond_ai.bots.registry import GENERAL_BOT, GENERAL_BOT_ID
from almond_ai.bots.storage import save_user_bots
from almond_ai.commands import COMMANDS, command_suggestions, parse_command
from almond_ai.config import DeveloperConfig
from almond_ai.core import AlmondCore
from almond_ai.integrations.registry import integration_registry
from almond_ai.models.provider import ModelProviderError
from almond_ai.rag.service import RAGStatus
from almond_ai.ui.screens.new_bot import NewBotScreen
from almond_ai.ui.screens.views import (
    AgentsView,
    ConsoleView,
    DeployView,
    EvaluationView,
    IntegrationsView,
    LogsView,
    PermissionsView,
    RAGView,
    SettingsView,
    ToolsView,
)
from almond_ai.ui.widgets.bot_sidebar import BotNavItem, BotSidebar, NewBotItem
from almond_ai.ui.widgets.console import CommandInput, ComposerTextArea
from almond_ai.ui.widgets.rag_results import render_rag_results
from almond_ai.ui.widgets.sidebar import NavItem, navigation_id
from app.errors import (
    ContentPolicyError,
    DocumentError,
    FirmAIError,
    PdfGenerationError,
    ProviderError,
)
from app.safety.content_filter import enforce_safe_input
from app.tools.calculator import (
    absolute_change,
    annual_allowance_position,
    carry_forward,
    pension_withdrawal_tax,
    percentage_return,
    to_decimal,
)

# Session id reserved for the real, visible TUI session.
# `ApplicationDispatcher` (almond_ai.control.dispatcher) drives this exact
# session when `almond ctl` is called with `--session live`, so commands
# and chat appear in the running console exactly as if typed manually.
# Any other session id is an isolated automation session: its chat
# history and pending confirmations never touch the visible console.
LIVE_SESSION = "live"

# Per-bot empty-state copy (AlmondDeveloperApp._update_empty_state). Not a
# generic "Welcome to Almond AI" block for every bot -- each specialist bot
# names its one capability and its current maturity instead.
EMPTY_STATE_BODY = {
    GENERAL_BOT_ID: "How can I help?",
    "calculator": (
        "Withdrawal tax, carry forward, and annual allowance -- calculated, never estimated."
    ),
    "drafting": "Draft polished client emails using the local model.",
    "document": "Turn any local file into a branded PDF.",
    "coding": "Experimental\nComing Soon",
}

CHAT_ROUTED_INSTRUCTIONS = {
    "summarise": "Summarise clearly and preserve material facts:",
    "draft": "Draft polished internal financial-services wording:",
    "analyse": "Analyse carefully, separating facts, risks, and assumptions:",
}
CHAT_ROUTED_COMMAND_NAMES = frozenset({"ask", *CHAT_ROUTED_INSTRUCTIONS})

_PDF_MENTION_RE = re.compile(r"\bpdf\b", re.IGNORECASE)
_PDF_VERB_RE = re.compile(r"\b(make|create|turn|convert|format|generate|produce)\b", re.IGNORECASE)
_QUOTED_RE = re.compile(r"[\"'‘’“”]([^\"'‘’“”]{1,200})[\"'‘’“”]")
_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+|\.{0,2}/[^\s\"']+")
_TITLE_PHRASE_RE = re.compile(r"\btitle[d]?\b\s*[:\-]?\s*[\"']?([^\"'\n,]{1,80})", re.IGNORECASE)
_FROM_PHRASE_RE = re.compile(r"\b(?:from|of|called|named)\s+(.+?)(?:[.?!]+\s*)?$", re.IGNORECASE)
_ALMOND_OUTPUT_STEM_RE = re.compile(r"-almond(-\d+)?$", re.IGNORECASE)

_CAPABILITY_CUE_RE = re.compile(
    r"\b(can|could|do|does|are|is|will)\b.{0,25}\byou\b|\b(unable|able)\b", re.IGNORECASE
)
_CAPABILITY_VERB_RE = re.compile(
    r"\b(access|read|open|view|see|look at|use|upload)\b", re.IGNORECASE
)
_FILE_NOUN_RE = re.compile(r"\bfiles?\b|\bdocuments?\b|\bpdfs?\b", re.IGNORECASE)

FILE_CAPABILITY_ANSWER = (
    "[b]Yes[/] — Almond reads real local files through two commands:\n\n"
    '[#F15A24]/pdf create <path> --title "Title"[/]\n'
    "  Works on ANY file, anywhere on your computer. No setup, no copying\n"
    "  it anywhere first. Accepts .txt .md .docx .pdf and images\n"
    "  (.png/.jpg/.jpeg/.bmp/.tiff, read via local OCR). Saves a branded\n"
    "  PDF straight to your Downloads folder.\n\n"
    "[#F15A24]/rag add <path>[/] then [#F15A24]/rag search <query>[/]\n"
    "  Only for files already copied into Almond's own documents folder —\n"
    "  use this for searching across many saved documents, not a one-off\n"
    "  file.\n\n"
    'Tell me which file, or just say something like "make a pdf from '
    "<file>\" and I'll build the command for you."
)


def is_file_capability_question(text: str) -> bool:
    """Catch 'can you access/read/open files' style questions.

    The local 2B model reliably answers these wrong (leads with a flat
    "No" even when told otherwise, or conflates /pdf and /rag's rules) no
    matter how the system prompt is worded -- so this bypasses the model
    entirely for the specific case of "can you touch files at all",
    answering deterministically instead. A concrete "make a pdf from X" is
    handled separately by _detect_pdf_intent and takes priority when a
    specific file is actually named.
    """
    return bool(
        _CAPABILITY_CUE_RE.search(text)
        and _CAPABILITY_VERB_RE.search(text)
        and _FILE_NOUN_RE.search(text)
    )


class HelpScreen(ModalScreen):
    """Scrollable command reference that never pollutes chat output."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("Command Palette", id="help-title")
            yield Static("\n".join(COMMANDS), id="help-commands")
            yield Static("Esc closes", id="help-close")

    def action_dismiss(self) -> None:
        self.dismiss()


class LoadingScreen(ModalScreen):
    """Splash shown while the bundled local model server warms up.

    The app is not reported "ready" (to a user at the composer, or to
    `almond ctl wait-ready`) until this dismisses -- so nothing has to
    eat the model's cold-start latency on its first real message.
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="loading-panel"):
            yield Static("Starting Almond AI…", id="loading-status")
            yield ProgressBar(id="loading-bar", total=None, show_eta=False, show_percentage=False)

    MIN_VISIBLE_SECONDS = 2.5

    def on_mount(self) -> None:
        self._elapsed = 0.0
        self._base_status = "Starting Almond AI…"
        self.set_interval(1.0, self._tick)
        self.run_worker(self._boot(), exclusive=True)

    def _tick(self) -> None:
        # Keeps the elapsed-time readout live while _boot() awaits astart().
        self._elapsed += 1.0
        status = self.query_one("#loading-status", Static)
        status.update(f"{self._base_status} ({int(self._elapsed)}s)")

    async def _boot(self) -> None:
        started = time.monotonic()
        status = self.query_one("#loading-status", Static)
        local_server = getattr(self.app.provider, "local_server", None)
        if local_server is not None:
            self._base_status = "Loading local model — this can take up to a minute…"
            status.update(self._base_status)
            try:
                await local_server.astart()
                self._base_status = "Model ready."
                status.update(self._base_status)
            except ProviderError as exc:
                status.update(f"[#D9534F]{escape(str(exc))}[/]")
                await asyncio.sleep(2)
        else:
            status.update("Ready.")
        elapsed = time.monotonic() - started
        remaining = self.MIN_VISIBLE_SECONDS - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self.dismiss()


class AlmondDeveloperApp(App):
    CSS_PATH = "ui/styles/almond.tcss"
    TITLE = "Almond Financial | AI Development Console"
    SUB_TITLE = f"v{__version__}"
    BINDINGS = [
        ("ctrl+c", "cancel_operation", "Cancel"),
        ("ctrl+l", "clear_console", "Clear"),
        ("ctrl+k", "clear_input", "Clear input"),
        ("escape", "close_overlay", "Close"),
        ("question_mark", "shortcuts", "Shortcuts"),
        ("up", "history_previous", "History"),
        ("down", "history_next", "History"),
        ("tab", "autocomplete", "Complete"),
        ("ctrl+o", "browse_file", "Browse"),
    ]
    VIEW_IDS = {
        "Chat": "view-chat",
        "Agents": "view-agents",
        "Tools": "view-tools",
        "Permissions": "view-permissions",
        "Data & RAG": "view-data-rag",
        "Integrations": "view-integrations",
        "Evaluation": "view-evaluation",
        "Logs": "view-logs",
        "Deploy": "view-deploy",
        "Settings": "view-settings",
    }

    def __init__(self, config: DeveloperConfig | None = None) -> None:
        super().__init__()
        # AlmondCore owns the provider, sessions, tools, RAG, permissions,
        # and PDF/audit services -- the same instance is what almond_ai.desktop
        # constructs too, so both UIs share exactly one model and one set of
        # backend services rather than each building their own.
        self.core = AlmondCore(config)
        self.config = self.core.config
        self.base_config = self.core.base_config
        self.provider = self.core.provider
        self.agents = self.core.agents
        self.tools = self.core.tools
        self.rag = self.core.rag
        self.permissions = self.core.permissions
        self.evals = self.core.evals
        self.logs = self.core.logs
        self.bots_path = self.core.bots_path
        self.history: list[str] = []
        self.history_index = 0
        self.started = time.monotonic()
        self.active_worker = None
        self.active_view = "Chat"
        self.console_transcript: list[str] = []
        self._automation_pending: dict[str, tuple[str, str]] = {}
        self.ready = False
        self.control_server = None
        # Bot/session layer: every bot is its own AgentSession (own messages,
        # status, pending confirmation) sharing this one provider instance.
        # `messages`/`pending_confirmation` below are properties delegating
        # to whichever bot session is currently active, so the rest of this
        # class -- and the control bridge, which reads/writes them directly
        # -- keeps working unchanged regardless of which bot is selected.
        self.sessions = self.core.sessions

    @property
    def messages(self) -> list[dict[str, str]]:
        return self.sessions.active().messages

    @property
    def pending_confirmation(self) -> tuple[str, str] | None:
        return self.sessions.active().pending_confirmation

    @pending_confirmation.setter
    def pending_confirmation(self, value: tuple[str, str] | None) -> None:
        self.sessions.active().pending_confirmation = value

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            yield BotSidebar(GENERAL_BOT, self.sessions.my_bots())
            with Vertical(id="center-shell"):
                with Vertical(id="center-header"):
                    yield Static("General Chat", id="welcome-heading", markup=True)
                    yield Static("Your local financial assistant", id="developer-heading")
                    yield Static("● Local    🔒 Private", id="workflow-heading", markup=True)
                with Vertical(id="view-stack"):
                    yield ConsoleView()
                    yield AgentsView(self.agents.list())
                    yield ToolsView(self.tools.list(), self.sessions.my_bots())
                    yield PermissionsView(
                        self.permissions,
                        self.tools.list(),
                        user_id=self.config.user_id,
                        role=self.config.role,
                        documents_dir=self.rag.documents_dir,
                        outputs_dir=self.base_config.outputs_dir,
                        data_dir=self.base_config.data_dir,
                        control_enabled=getattr(self.config, "control_enabled", False),
                    )
                    # Placeholder only: real status is computed off-thread in
                    # _load_rag_status_async() and applied once mounted.
                    # Scanning data/sample_documents re-parses every allowed
                    # file from scratch (no cache), and a large PDF there can
                    # take well over a minute -- doing that synchronously
                    # here, inside compose(), used to block the entire first
                    # render and made the app look frozen on launch.
                    yield RAGView(
                        RAGStatus(
                            0,
                            0,
                            "local keyword index",
                            self.config.embedding_model,
                            indexing="loading…",
                        )
                    )
                    yield IntegrationsView(
                        integration_registry(self.rag.documents_dir, self.config.model)
                    )
                    yield EvaluationView(self.evals.list())
                    yield LogsView(id="view-logs", classes="view")
                    yield DeployView(self.config)
                    yield SettingsView(self.config)
                yield CommandInput(id="input-area")
        yield Static(
            "Almond Financial | Internal Use Only     Secure | Private | Local     "
            "Enter submit     ? shortcuts",
            id="secure-footer",
        )

    async def _load_rag_status_async(self) -> None:
        status = await asyncio.to_thread(self.rag.status)
        self._update_status(rag=status)
        values = {
            "rag-status": status.indexing,
            "rag-documents": str(status.documents),
            "rag-chunks": str(status.chunks),
            "rag-embedding": status.embedding_model,
            "rag-last-index": status.last_index,
            "rag-vector-store": status.database,
        }
        for widget_id, value in values.items():
            self.query_one(f"#{widget_id}", Static).update(escape(value))

    def on_mount(self) -> None:
        self.query_one(BotSidebar).set_active_bot(GENERAL_BOT_ID)
        self._update_header()
        self._update_empty_state()
        # Real RAG status (documents/chunks) isn't known yet -- computing it
        # can mean re-parsing every file in data/sample_documents, including
        # any large PDFs, from scratch. _load_rag_status_async() below fills
        # it in for real once that's done; this placeholder just keeps
        # on_mount() itself fast so the loading screen appears immediately.
        # Deferred via call_after_refresh: #system-status lives inside
        # SettingsView, one of several View widgets whose own nested
        # composition (Card -> Static) mounts asynchronously after this
        # method runs -- querying it synchronously here race against that
        # mount under load and intermittently raised NoMatches.
        self.call_after_refresh(
            self._update_status,
            rag=RAGStatus(
                0, 0, "local keyword index", self.config.embedding_model, indexing="loading…"
            ),
        )
        if getattr(self.config, "control_enabled", False):
            self._start_control_server()
        self.push_screen(LoadingScreen(), callback=self._on_loading_complete)
        # Deliberately NOT started here (see _on_loading_complete): the RAG
        # scan re-parses every document in data/sample_documents from
        # scratch on every launch (no persistent cache -- see
        # RAGService._all_chunks). That's CPU-bound pure-Python work, which
        # holds the GIL and starves the event loop that LoadingScreen needs
        # to poll the local model's readiness -- running it concurrently
        # with model startup was making the loading screen take far longer
        # than the model itself actually needs.

    def _on_loading_complete(self, _result: None = None) -> None:
        self.query_one("#composer", TextArea).focus()
        self.ready = True
        # Cheap status update only (AI Online/Offline label) -- NOT a full
        # self._update_status(), which would call self.rag.status() and
        # block this exact moment on the same expensive re-scan described
        # above. _load_rag_status_async(), started right after, fills in
        # the real RAG numbers off-thread once the app is already usable.
        self._update_status(
            rag=RAGStatus(
                0, 0, "local keyword index", self.config.embedding_model, indexing="loading…"
            )
        )
        self.run_worker(self._load_rag_status_async(), group="rag-status", exclusive=True)

    def on_unmount(self) -> None:
        stop = getattr(self.provider, "stop", None)
        if stop is not None:
            stop()
        if self.control_server is not None:
            asyncio.create_task(self.control_server.stop())

    def _start_control_server(self) -> None:
        """Start the local developer control bridge (disabled by default).

        Imported lazily to avoid a module-level import cycle: the control
        package imports session/routing constants from this module.
        """
        from almond_ai.control.dispatcher import ApplicationDispatcher
        from almond_ai.control.server import ControlServer

        dispatcher = ApplicationDispatcher(self)
        runtime_dir = Path(self.base_config.data_dir) / "runtime"
        self.control_server = ControlServer(dispatcher, runtime_dir)
        self.run_worker(self.control_server.start(), group="control-server", exclusive=False)

    def _log(self, text: str) -> None:
        """Write to the visible console and mirror it in the plain-text transcript.

        The transcript, not the RichLog's rendered/wrapped Strip buffer, is
        what the control bridge reads for `ctl snapshot` and to capture a
        live session's response text -- every write to "#console" must go
        through here so that transcript stays complete and in order.
        """
        self.query_one("#console", RichLog).write(text)
        self.console_transcript.append(text)

    def _update_status(self, rag: RAGStatus | None = None) -> None:
        rag = rag if rag is not None else self.rag.status()
        integrations = integration_registry(self.rag.documents_dir, self.config.model)
        integration_count = sum(item.status == "online" for item in integrations)
        uptime = int(time.monotonic() - self.started)
        provider = "mock" if self.config.model.provider == "fake" else self.config.model.provider
        ready_check = getattr(self.provider, "is_ready", lambda: False)
        model_online = bool(ready_check())
        if self.config.model.provider == "fake":
            ai_label, ai_tone = "AI Mock", "#B58A52"
        elif model_online:
            ai_label, ai_tone = "AI Online", "#6F9B74"
        elif not self.ready:
            # Startup: the loading screen is still warming the local model
            # up (see LoadingScreen._boot) -- it genuinely isn't up yet, but
            # calling that "AI Ready" or "AI Online" would be a false claim.
            ai_label, ai_tone = "AI Starting", "#B58A52"
        else:
            # App finished starting, but the provider is still not
            # reachable -- this is a real outage, not a "ready" state.
            ai_label, ai_tone = "AI Offline", "#A96363"
        environment = "DEV / MOCK" if self.config.model.provider == "fake" else "DEVELOPMENT"
        self.query_one("#system-status", Static).update(
            f"[{ai_tone}]● {ai_label}[/]    [#B58A52]{environment}[/]\n\n"
            f"[#9CA3A8]Model[/]          {escape(self.config.model.model)}\n"
            f"[#9CA3A8]Provider[/]       {escape(provider)}\n"
            "[#9CA3A8]Runtime[/]        local/private\n"
            f"[#9CA3A8]RAG[/]            {rag.chunks} chunks\n"
            f"[#9CA3A8]Integrations[/]   {integration_count}/{len(integrations)} online\n"
            f"[#9CA3A8]Uptime[/]         {uptime}s"
        )
        self.query_one("#workflow-heading", Static).update(f"[{ai_tone}]●[/] Local    🔒 Private")

    def _active_bot(self) -> BotDefinition:
        return self.sessions.bots[self.sessions.active().bot_id]

    def _system_prompt_for_bot(self, bot_id: str) -> str:
        return self.core.system_prompt_for_bot(bot_id)

    def _update_header(self) -> None:
        """Bot name/description/composer label only -- no readiness probe.

        `LocalModelServer.is_ready()` opens a real (loopback) socket
        connection, which is fine occasionally but must never run
        synchronously on every bot switch, and especially not from
        `on_mount()` before the LoadingScreen splash has even appeared --
        that delayed the splash itself. The "● Local" dot is refreshed
        separately, only by `_update_status()`, which already knows the
        real readiness state without probing again here.
        """
        bot = self._active_bot()
        self.query_one("#welcome-heading", Static).update(f"[b]{escape(bot.name)}[/]")
        self.query_one("#developer-heading", Static).update(escape(bot.description))
        self.query_one("#input-label", Label).update(f"> Message {escape(bot.name)}…")

    def _update_empty_state(self) -> None:
        """Rewrite the empty-state text and show at most one quick-action
        button, matching whichever bot is active -- hidden entirely once
        that bot has any messages.
        """
        bot = self._active_bot()
        panel = self.query_one("#welcome-panel")
        panel.styles.display = "none" if self.messages else "block"
        body = EMPTY_STATE_BODY.get(bot.id, "Ask anything.")
        self.query_one("#welcome-text", Static).update(
            f"[b]{escape(bot.name)}[/]\n\n[#9CA3A8]{body}[/]"
        )
        for button in self.query(".quick-action"):
            button.styles.display = "block" if button.id == f"quick-action-{bot.id}" else "none"

    def _render_active_session(self) -> None:
        """Replace the visible console with the active bot's own history."""
        console = self.query_one("#console", RichLog)
        console.clear()
        self.console_transcript.clear()
        for message in self.messages:
            if message["role"] == "user":
                self._log(f"\n[#F15A24]>[/] {escape(message['content'])}")
            elif message["role"] == "assistant":
                self._log(f"[b]Almond[/b]  {escape(message['content'].strip())}")
        self._update_empty_state()

    def switch_bot(self, bot_id: str) -> None:
        self.sessions.switch(bot_id)
        self.show_view("Chat")
        self._render_active_session()
        self._update_header()
        self.query_one(BotSidebar).set_active_bot(bot_id)

    @on(BotNavItem.Selected)
    def on_bot_selected(self, event: BotNavItem.Selected) -> None:
        self.switch_bot(event.bot_id)

    @on(Button.Pressed, "#quick-action-calculator")
    def on_run_calculator_quick_action(self) -> None:
        editor = self.query_one("#composer", TextArea)
        editor.load_text("/tool run pension_withdrawal_tax <withdrawal> [other_taxable_income]")
        editor.focus()

    @on(Button.Pressed, "#quick-action-drafting")
    def on_draft_client_email_quick_action(self) -> None:
        editor = self.query_one("#composer", TextArea)
        editor.load_text(
            "Draft a client email.\n"
            "Purpose: \n"
            "Client context: \n"
            "Tone (optional): \n"
            "Key points (optional): "
        )
        editor.focus()

    @on(Button.Pressed, "#quick-action-document")
    def on_create_pdf_quick_action(self) -> None:
        self._browse_file()

    @on(NewBotItem.Requested)
    def on_new_bot_requested(self) -> None:
        existing_ids = frozenset(self.sessions.bots.keys())
        self.push_screen(NewBotScreen(existing_ids), callback=self._on_new_bot_created)

    def _on_new_bot_created(self, bot: BotDefinition | None) -> None:
        if bot is None:
            return
        self.sessions.add_bot(bot)
        user_bots = [b for b in self.sessions.bots.values() if not b.built_in]
        save_user_bots(self.bots_path, user_bots)
        self.query_one(BotSidebar).add_bot_item(bot)
        self.logs.add("bots", "INFO", f"Created bot: {bot.name}")
        self.switch_bot(bot.id)

    def _set_bot_status(self, bot_id: str, status: str) -> None:
        session = self.sessions.get(bot_id)
        session.status = status
        session.touch()
        try:
            item = self.query_one(f"#bot-{bot_id}", BotNavItem)
        except NoMatches:
            return
        item.set_status(status)

    def show_view(self, name: str) -> None:
        if name not in self.VIEW_IDS:
            raise ValueError(f"Unknown view: {name}")
        for view in self.query(".view"):
            view.remove_class("view-active")
        self.query_one(f"#{self.VIEW_IDS[name]}").add_class("view-active")
        for item in self.query(NavItem):
            item.remove_class("nav-selected")
        matches = self.query(f"#{navigation_id(name)}")
        if matches:
            matches.first().add_class("nav-selected")
        if name == "Chat":
            self.query_one(BotSidebar).set_active_bot(self.sessions.active_id)
        elif name == "Settings":
            self.query_one(BotSidebar).set_active_settings()
        self.active_view = name
        if name == "Logs":
            self._refresh_logs()

    def _refresh_logs(self) -> None:
        output = self.query_one("#logs-console", RichLog)
        output.clear()
        entries = self.logs.filter()
        if not entries:
            output.write("[#9CA3A8]No runtime events recorded.[/]")
            return
        for entry in entries:
            output.write(
                f"{entry.timestamp} {entry.subsystem:<12} {entry.severity:<7} "
                f"{entry.request_id} {escape(entry.message)}"
            )

    def _refresh_evaluations(self) -> None:
        results = {result.name: result for result in self.evals.results()}
        for suite in self.evals.list():
            result = results.get(suite.name)
            detail = "Never run"
            latency = "—"
            if result:
                detail = escape(result.detail)
                latency = f"{result.latency_ms} ms"
            self.query_one(f"#eval-result-{suite.name}", Static).update(
                f"[#9CA3A8]Category[/]  {suite.category}\n"
                f"[#9CA3A8]Latency[/]   {latency}\n"
                f"[#9CA3A8]Result[/]    {suite.status}\n"
                f"[#9CA3A8]Detail[/]    {detail}"
            )

    async def _provider_probe(self) -> tuple[bool, str]:
        response = ""
        async for chunk in self.provider.stream(
            [{"role": "user", "content": "Reply with a brief readiness acknowledgement."}]
        ):
            response += chunk
        return bool(response.strip()), f"{self.provider.name} returned {len(response)} characters"

    def _permission_probe(self) -> tuple[bool, str]:
        try:
            self.tools.authorize_run("document_search", set())
        except PermissionError:
            return True, "Missing permission denied correctly"
        return False, "Permission boundary failed open"

    async def _run_probe_suite(self, requested: str) -> list[tuple[str, object]]:
        """Run one or all evaluation probes and return (name, EvaluationResult) pairs.

        Shared by the live console worker and the automation-session ctl
        path so both run the exact same probes against the exact same
        registry instead of duplicating the probe definitions.
        """
        probes = {
            "prompt-safety": lambda: (
                enforce_safe_input("Summarise approved onboarding guidance")
                == "Summarise approved onboarding guidance",
                "Safe prompt accepted",
            ),
            "retrieval-baseline": lambda: (
                self.rag.status().failed_documents == 0,
                f"{self.rag.status().documents} documents scanned",
            ),
            "tool-permissions": self._permission_probe,
            "provider-latency": self._provider_probe,
        }
        names = list(probes) if requested == "all" else [requested]
        results = []
        for name in names:
            result = await self.evals.run(name, probes[name])
            self.logs.add("evaluation", "INFO" if result.passed else "ERROR", result.detail)
            results.append((name, result))
        self._refresh_evaluations()
        return results

    @work(exclusive=False, group="evaluations")
    async def run_evaluations(self, requested: str) -> None:
        results = await self._run_probe_suite(requested)
        for name, result in results:
            tone = "#6F9B74" if result.passed else "#A96363"
            self._log(
                f"[{tone}]{name}: {'PASS' if result.passed else 'FAIL'}[/] "
                f"{result.latency_ms} ms — {escape(result.detail)}"
            )

    @on(TextArea.Changed, "#composer")
    def show_suggestions(self, event: TextArea.Changed) -> None:
        value = event.text_area.text.lstrip()
        box = self.query_one("#suggestions", Static)
        if value.startswith("/"):
            matches = command_suggestions(value)
            box.update("\n".join(matches) if matches else "No matching commands")
            box.styles.display = "block"
        else:
            box.styles.display = "none"

    @on(ComposerTextArea.Submitted)
    def on_composer_submitted(self) -> None:
        self.submit_input()

    def submit_input(self) -> None:
        editor = self.query_one("#composer", TextArea)
        text = editor.text.strip()
        if not text:
            return
        editor.clear()
        self.query_one("#suggestions", Static).styles.display = "none"
        self.history.append(text)
        self.history_index = len(self.history)
        self.show_view("Chat")
        self._log(f"\n[#F15A24]>[/] {escape(text)}")
        if self.pending_confirmation:
            action, required = self.pending_confirmation
            self.pending_confirmation = None
            if text == required:
                try:
                    if action.startswith("RAG "):
                        message = self._perform_rag_action(action)
                        self._log(f"[#6F9B74]{escape(message)}[/]")
                    elif action.startswith("TOOL "):
                        output = self._perform_tool_action(action)
                        self._log(output)
                    elif action.startswith("PDF "):
                        output = self._perform_pdf_action(action)
                        self._log(output)
                    else:
                        self._log(f"[#D0A15A]DEV / MOCK — {escape(action)} adapter unavailable.[/]")
                        self.logs.add("deploy", "WARNING", f"Confirmed mock action: {action}")
                except (ValueError, PermissionError, FirmAIError) as exc:
                    self._log(f"[#A96363]Error[/] {escape(str(exc))}")
                    self.logs.add("rag", "ERROR", str(exc))
            else:
                self._log("[#9CA3A8]Confirmation rejected. Operation cancelled.[/]")
            return
        parsed = parse_command(text)
        if parsed:
            self.run_command(parsed.name, parsed.args)
            return
        nl_pdf = self._detect_pdf_intent(text)
        if nl_pdf:
            path, title = nl_pdf
            self._set_pending(LIVE_SESSION, (f"PDF {path}|||{title}", "CONFIRM"))
            self._log(
                f"[#D0A15A]Found:[/] {escape(Path(path).name)}\n"
                f'Create a branded PDF titled "{escape(title)}"? Type CONFIRM to continue, '
                "or type anything else to cancel."
            )
            return
        pdf_request = self._extract_pdf_request(text)
        if pdf_request and pdf_request[0]:
            candidate = pdf_request[0]
            searched = ", ".join(str(root) for root in self._pdf_search_roots())
            self._log(
                f'[#A96363]Couldn\'t find a file matching "{escape(candidate)}"[/] as a '
                f"direct path, or (uniquely) in: {escape(searched)}\n"
                "Give me the exact path instead (forward slashes, e.g. "
                "C:/Users/you/Desktop/file.docx), or move the file into one of "
                "those folders and try again."
            )
            return
        if is_file_capability_question(text):
            self._log(FILE_CAPABILITY_ANSWER)
            return
        self.run_chat(text)

    def _perform_rag_action(self, action: str) -> str:
        self.tools.authorize_run("rag_reindex", self.permissions, confirmed=True)
        verb, _, target = action[4:].partition(" ")
        if verb == "reindex":
            status = self.rag.reindex()
            message = f"Index refreshed: {status.documents} documents, {status.chunks} chunks."
        elif verb == "add":
            record = self.rag.add(target)
            message = f"Indexed {record.filename}: {len(record.chunks)} chunks."
        elif verb == "remove":
            count = self.rag.remove(target)
            message = f"Excluded {count} document(s). Source files unchanged."
        else:
            raise ValueError(f"Unknown RAG action: {verb}")
        self.logs.add("rag", "INFO", message)
        self._refresh_rag_status()
        return message

    def _perform_tool_action(self, action: str) -> str:
        parts = action.split()
        tool = self.tools.get(parts[1])
        self.tools.authorize_run(tool.name, self.permissions, confirmed=True)
        return self._execute_tool(tool, tuple(parts[2:]))

    def _execute_tool(self, tool, tool_args: tuple[str, ...]) -> str:
        if tool.name == "document_search":
            if not tool_args:
                raise ValueError("Usage: /tool run document_search <query>")
            result = self.rag.search(
                " ".join(tool_args), self.config.user_id, self.config.rag_top_k
            )
            output = render_rag_results(result)
        elif tool.name == "calculator":
            output = self._calculate(tool_args)
        elif tool.name == "rag_reindex":
            status = self.rag.reindex()
            output = f"Index refreshed: {status.documents} documents, {status.chunks} chunks."
            self._refresh_rag_status()
        elif tool.name in {"pension_withdrawal_tax", "carry_forward", "annual_allowance"}:
            output = self._calculate_pension(tool.name, tool_args)
        elif tool.name == "local_development":
            # Coding bot's signature capability -- genuinely not built yet.
            # Never touch files/shell/SQL here.
            output = "Local development agent is still in development."
        elif tool.name == "draft_client_email":
            output = (
                "Describe the email in the composer -- purpose, client context, and "
                "optionally tone and key points -- and Drafting will write it using the "
                "local model. Try the Draft Client Email quick action below."
            )
        else:
            raise ValueError(f"Tool execution unavailable: {tool.name}")
        tool.last_status = "success"
        self.logs.add("tools", "INFO", f"{tool.name} completed")
        return output

    def _refresh_rag_status(self) -> None:
        status = self.rag.status()
        values = {
            "rag-status": status.indexing,
            "rag-documents": str(status.documents),
            "rag-chunks": str(status.chunks),
            "rag-embedding": status.embedding_model,
            "rag-last-index": status.last_index,
            "rag-vector-store": status.database,
        }
        for widget_id, value in values.items():
            self.query_one(f"#{widget_id}", Static).update(escape(value))

    @work(exclusive=True)
    async def run_chat(self, prompt: str) -> None:
        # Bot/session pinned up front, not re-read via the `self.messages`/
        # active-session properties as this runs -- if the user switches to
        # a different bot before this finishes, this response must still
        # land in the bot it was actually asked of, not whichever bot
        # happens to be active when the model reply arrives.
        bot_id = self.sessions.active_id
        try:
            prompt = enforce_safe_input(prompt)
        except ContentPolicyError as exc:
            self._log_if_active(bot_id, f"[#A96363]{escape(str(exc))}[/]")
            return

        def visible() -> bool:
            return self.sessions.active_id == bot_id

        self._set_bot_status(bot_id, STATUS_THINKING)
        self._log_if_active(bot_id, "[#9CA3A8]Thinking…[/]")
        self.core.append_user_message(bot_id, prompt)
        if visible():
            self._update_empty_state()
        indicator = self.query_one("#stream-indicator", Static)
        response = ""
        try:
            async for chunk in self.core.stream_reply(bot_id):
                response += chunk
                if visible():
                    preview = " ".join(response.strip().splitlines())[-70:]
                    indicator.styles.display = "block"
                    indicator.update(f"[#9CA3A8]Almond is typing… {escape(preview)}[/]")
            self._log_if_active(bot_id, f"[b]Almond[/b]  {escape(response.strip())}")
            self.logs.add("model", "INFO", "Model response completed")
            if visible():
                self._update_status()
            self._set_bot_status(bot_id, STATUS_COMPLETE)
        except ModelProviderError as exc:
            self._log_if_active(bot_id, "[#A96363][b]Error[/b][/]")
            self._log_if_active(
                bot_id,
                f"Model connection failed.\nProvider: {escape(self.provider.name)}\n"
                f"Endpoint: {escape(str(self.config.model.base_url))}\nRetry from Logs.",
            )
            self.logs.add("model", "ERROR", str(exc))
            self._set_bot_status(bot_id, STATUS_ERROR)
        finally:
            if visible():
                indicator.update("")
                indicator.styles.display = "none"

    def _log_if_active(self, bot_id: str, text: str) -> None:
        """Write to the visible console only if `bot_id` is still selected.

        Prevents a background bot's output from appearing to come from
        whichever bot happens to be on screen when it finishes.
        """
        if self.sessions.active_id == bot_id:
            self._log(text)

    def run_command(self, name: str, args: tuple[str, ...], session: str = LIVE_SESSION) -> None:
        try:
            output = self._command_output(name, args, session)
            if output:
                self._log(output)
        except (ValueError, PermissionError, FirmAIError) as exc:
            self._log(f"[#A96363]Error[/] {escape(str(exc))}")
            self.logs.add("tools", "ERROR", str(exc))
        self._update_status()

    def _set_pending(self, session: str, value: tuple[str, str] | None) -> None:
        """Record a pending write-confirmation, scoped to `session`.

        The live session's slot is the `pending_confirmation` property,
        which now delegates to whichever bot is currently active (see
        `AgentSession.pending_confirmation`) -- so it's the confirmation
        state of the visible bot specifically, not a single global slot.
        Every other (automation) session gets its own entry in
        `_automation_pending` so a scripted command can never be confirmed
        by the real operator typing CONFIRM in the visible console, or vice
        versa.
        """
        if session == LIVE_SESSION:
            self.pending_confirmation = value
        elif value is None:
            self._automation_pending.pop(session, None)
        else:
            self._automation_pending[session] = value

    def _agents_text(self) -> str:
        return "\n".join(f"{agent.name}: {agent.description}" for agent in self.agents.list())

    def _tools_text(self) -> str:
        return "\n".join(
            f"{tool.name} ({'enabled' if tool.enabled else 'disabled'})"
            for tool in self.tools.list()
        )

    def _permissions_text(self) -> str:
        granted = ", ".join(sorted(self.permissions)) or "(none granted)"
        lines = [
            f"User: {self.config.user_id}  Role: {self.config.role}",
            f"Granted: {granted}",
            f"Read/index root (RAG): {self.rag.documents_dir}",
            f"PDF output folder: {self.base_config.outputs_dir}",
            f"App data folder: {self.base_config.data_dir}",
            "No outbound network calls from any tool or the local model.",
            "Developer control bridge: "
            + (
                "ENABLED (loopback only)"
                if getattr(self.config, "control_enabled", False)
                else "disabled"
            ),
            "",
            "Tools:",
        ]
        for tool in self.tools.list():
            have_it = tool.required_permission in self.permissions
            lines.append(
                f"  {tool.name}: {'enabled' if tool.enabled else 'disabled'}, "
                f"requires {tool.required_permission} ({'have it' if have_it else 'missing'}), "
                f"{'needs CONFIRM' if tool.approval_required else 'runs immediately'}"
            )
        return "\n".join(lines)

    def _rag_status_text(self) -> str:
        status = self.rag.status()
        return (
            f"Indexing: {status.indexing}\nDocuments: {status.documents}\n"
            f"Chunks: {status.chunks}\nEmbedding: {status.embedding_model}\n"
            f"Last index: {status.last_index}\nStore: {status.database}"
        )

    def _integrations_text(self) -> str:
        integrations = integration_registry(self.rag.documents_dir, self.config.model)
        return "\n".join(f"{item.name}: {item.status}" for item in integrations)

    def _eval_results_text(self) -> str:
        results = {result.name: result for result in self.evals.results()}
        lines = []
        for suite in self.evals.list():
            result = results.get(suite.name)
            detail = "Never run" if result is None else result.detail
            lines.append(f"{suite.name}: {suite.status} — {detail}")
        return "\n".join(lines)

    def _logs_text(self, limit: int = 20) -> str:
        entries = self.logs.filter()[-limit:]
        if not entries:
            return "No runtime events recorded."
        return "\n".join(
            f"{entry.timestamp} {entry.subsystem:<12} {entry.severity:<7} {entry.message}"
            for entry in entries
        )

    def _deploy_status_text(self) -> str:
        return f"Almond version {__version__}. Deploy status: idle (no deployment adapter)."

    def _command_output(
        self, name: str, args: tuple[str, ...], session: str = LIVE_SESSION
    ) -> str | None:
        if name == "help":
            if session != LIVE_SESSION:
                return "\n".join(COMMANDS)
            self.push_screen(HelpScreen())
            return None
        if name == "clear":
            if session == LIVE_SESSION:
                self.action_clear_console()
            return None
        if name == "exit":
            if session != LIVE_SESSION:
                raise ValueError("/exit requires --session live")
            self.exit()
            return None
        if name == "agent":
            if not args or args[0] == "list":
                if session != LIVE_SESSION:
                    return self._agents_text()
                self.show_view("Agents")
                return None
            if args[0] == "status":
                agent = self.agents.status()
                return f"Active agent: [#F15A24]{agent.name}[/] — {agent.description}"
            if args[0] == "use" and len(args) == 2:
                agent = self.agents.use(args[1])
                self.logs.add("agents", "INFO", f"Active agent changed to {agent.name}")
                return f"Active agent: [#F15A24]{agent.name}[/]"
            raise ValueError("Usage: /agent list|status|use <name>")
        if name in {"tools", "tool"}:
            if name == "tools" or not args:
                if session != LIVE_SESSION:
                    return self._tools_text()
                self.show_view("Tools")
                return None
            verb = args[0]
            if len(args) < 2:
                raise ValueError("Tool name required")
            tool = self.tools.get(args[1])
            if verb == "inspect":
                return f"{tool.name}\n{tool.description}\nPermission: {tool.required_permission}"
            if verb in {"enable", "disable"}:
                self.tools.set_enabled(tool.name, verb == "enable", self.permissions)
                return f"{tool.name}: {verb}d"
            if verb == "run":
                tool_args = args[2:]
                if tool.approval_required:
                    target = f" {' '.join(tool_args)}" if tool_args else ""
                    self._set_pending(session, (f"TOOL {tool.name}{target}", "CONFIRM"))
                    return f"Tool {tool.name} requires approval. Type CONFIRM to continue:"
                self.tools.authorize_run(tool.name, self.permissions)
                return self._execute_tool(tool, tool_args)
            raise ValueError("Unknown tool action")
        if name == "permissions":
            if session != LIVE_SESSION:
                return self._permissions_text()
            self.show_view("Permissions")
            return None
        if name == "pdf":
            return self._handle_pdf_command(args)
        if name in {"rag", "search"}:
            verb = args[0] if name == "rag" and args else "search"
            rest = args[1:] if name == "rag" else args
            if verb == "status":
                if session != LIVE_SESSION:
                    return self._rag_status_text()
                self.show_view("Data & RAG")
                return None
            if verb == "search" and rest:
                result = self.rag.search(" ".join(rest), self.config.user_id, self.config.rag_top_k)
                return render_rag_results(result)
            if verb == "inspect" and rest:
                chunks = self.rag.inspect(" ".join(rest))
                if not chunks:
                    return "Document not found."
                chunk = chunks[0]
                return (
                    f"[b]{escape(chunk.filename)}[/b]\npath={escape(chunk.relative_path)} | "
                    f"title={escape(chunk.title)} | chunks={len(chunks)}"
                )
            if verb in {"add", "remove", "reindex"}:
                if verb in {"add", "remove"} and not rest:
                    raise ValueError(f"Usage: /rag {verb} <document>")
                target = f" {' '.join(rest)}" if rest else ""
                self._set_pending(session, (f"RAG {verb}{target}", "CONFIRM"))
                return f"Write operation: RAG {verb}. Type CONFIRM to continue:"
            raise ValueError("Usage: /rag status|search <query>|inspect <document>|reindex")
        if name in {"integrations", "integration"}:
            if name == "integration" and len(args) >= 2:
                verb, target = args[0], " ".join(args[1:]).casefold()
                integrations = integration_registry(self.rag.documents_dir, self.config.model)
                matches = [item for item in integrations if item.name.casefold() == target]
                if not matches:
                    raise ValueError(f"Unknown integration: {target}")
                item = matches[0]
                if verb == "inspect":
                    return f"{item.name}: {item.status} · {item.permissions}"
                if verb == "test":
                    return f"Health check: {item.name} — {item.status} (read-only probe)"
            if session != LIVE_SESSION:
                return self._integrations_text()
            self.show_view("Integrations")
            return None
        if name == "eval":
            if args and args[0] == "run":
                suite = args[1] if len(args) > 1 else "all"
                known = {item.name for item in self.evals.list()}
                if suite != "all" and suite not in known:
                    raise ValueError(f"Unknown evaluation suite: {suite}")
                self.run_evaluations(suite)
                return f"Evaluation started: {suite}"
            if session != LIVE_SESSION:
                return self._eval_results_text()
            if args and args[0] in {"results", "compare"}:
                self.show_view("Evaluation")
                self._refresh_evaluations()
                return None
            self.show_view("Evaluation")
            return None
        if name == "logs":
            if session != LIVE_SESSION:
                return self._logs_text()
            self.show_view("Logs")
            return None
        if name == "deploy":
            target = args[0] if args else "status"
            if target == "status":
                if session != LIVE_SESSION:
                    return self._deploy_status_text()
                self.show_view("Deploy")
                return None
            if target in {"production", "staging"}:
                self._set_pending(session, (f"{target} deployment", "DEPLOY"))
                return f"Deploy version {__version__} to {target.upper()}?\nType DEPLOY to confirm:"
        if name == "rollback":
            self._set_pending(session, ("rollback", "ROLLBACK"))
            return "Write operation: rollback. Type ROLLBACK to confirm:"
        if name == "config":
            if session != LIVE_SESSION:
                return json.dumps(self.config.safe_summary(), indent=2)
            self.show_view("Settings")
            return None
        if name == "ask":
            if not args:
                raise ValueError("Usage: /ask <question>")
            self.run_chat(" ".join(args))
            return None
        if name == "calc":
            return self._calculate(args)
        if name in {"summarise", "draft", "analyse"}:
            if not args:
                raise ValueError(f"Usage: /{name} <text>")
            self.run_chat(f"{CHAT_ROUTED_INSTRUCTIONS[name]}\n\n{' '.join(args)}")
            return None
        raise ValueError(f"Unknown command: /{name}")

    @staticmethod
    def _calculate(args: tuple[str, ...]) -> str:
        if len(args) != 3 or args[0] not in {"percentage-return", "absolute-change"}:
            raise ValueError("Usage: /calc percentage-return|absolute-change <start> <end>")
        operation, start_value, end_value = args
        start = to_decimal(start_value)
        end = to_decimal(end_value)
        value = (
            percentage_return(start, end)
            if operation == "percentage-return"
            else absolute_change(start, end)
        )
        suffix = "%" if operation == "percentage-return" else ""
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return f"{operation}: [#F15A24]{rendered}{suffix}[/]"

    @staticmethod
    def _calculate_pension(tool_name: str, args: tuple[str, ...]) -> str:
        if tool_name == "pension_withdrawal_tax":
            if len(args) not in (1, 2):
                raise ValueError(
                    "Usage: /tool run pension_withdrawal_tax <withdrawal> [other_taxable_income]"
                )
            withdrawal = to_decimal(args[0])
            other_income = to_decimal(args[1]) if len(args) == 2 else Decimal("0")
            result = pension_withdrawal_tax(withdrawal, other_income)
            return (
                f"Tax-free: £{result['tax_free_amount']} · Taxable: £{result['taxable_amount']} · "
                f"Tax due: £{result['tax_due']} · Net: £{result['net_amount']}"
            )
        if tool_name == "carry_forward":
            if not args or len(args) % 2 != 0 or len(args) > 6:
                raise ValueError(
                    "Usage: /tool run carry_forward <allowance1> <used1> [...] (up to 3 years)"
                )
            values = [to_decimal(a) for a in args]
            prior_years = tuple(zip(values[0::2], values[1::2], strict=True))
            result = carry_forward(prior_years)
            return (
                f"Unused carried forward: £{result['total_carry_forward']} · "
                f"Available this year: £{result['total_available_this_year']}"
            )
        if not args or len(args) > 7:
            raise ValueError(
                "Usage: /tool run annual_allowance <net_income> [salary_sacrifice] "
                "[relief_at_source_contributions] [net_pay_contributions] "
                "[employer_contributions] [db_pension_input] "
                "[taxable_lump_sum_death_benefit]"
            )
        values = [to_decimal(a) for a in args] + [Decimal("0")] * (7 - len(args))
        result = annual_allowance_position(*values)
        tapered_note = " (tapered)" if result["tapered"] else ""
        return (
            f"Threshold income: £{result['threshold_income']} · "
            f"Adjusted income: £{result['adjusted_income']} · "
            f"Applicable annual allowance{tapered_note}: £{result['annual_allowance']}"
        )

    def _extract_pdf_request(self, text: str) -> tuple[str | None, str | None] | None:
        """Pull a (candidate-filename-or-None, explicit-title-or-None) pair out

        of a plain-English PDF request, e.g. 'make a pdf from the file called
        X'. Returns None entirely when the text isn't a PDF-making request at
        all (no PDF mention, or no making verb) -- that case should fall
        through to normal chat. A non-None result with a None candidate means
        "this looks like a PDF request but no filename could be parsed out of
        it", which also isn't actionable.
        """
        if not _PDF_MENTION_RE.search(text) or not _PDF_VERB_RE.search(text):
            return None

        title_match = _TITLE_PHRASE_RE.search(text)
        explicit_title = title_match.group(1).strip() if title_match else None

        path_match = _PATH_RE.search(text)
        candidate = path_match.group(0).rstrip(".,;:") if path_match else None

        if candidate is None:
            quotes = _QUOTED_RE.findall(text)
            if explicit_title:
                quotes = [q for q in quotes if q.strip() != explicit_title]
            candidate = quotes[0] if quotes else None

        if candidate is None:
            from_match = _FROM_PHRASE_RE.search(text)
            candidate = from_match.group(1).strip("'\" ") if from_match else None

        return candidate, explicit_title

    def _detect_pdf_intent(self, text: str) -> tuple[str, str] | None:
        """Returns (resolved_path, title) only when a PDF request names a

        file that resolves to exactly one real file -- anything ambiguous or
        unresolvable returns None so the caller can fall back to a clear
        "couldn't find it" message instead of guessing.
        """
        request = self._extract_pdf_request(text)
        if not request or not request[0]:
            return None
        candidate, explicit_title = request

        resolved = self._resolve_pdf_candidate(candidate)
        if resolved is None:
            return None

        title = explicit_title or resolved.stem
        return str(resolved), title

    def _pdf_search_roots(self) -> list[Path]:
        """Folders searched for a bare filename mentioned in plain English.

        Not a whole-drive search: the app's own documents/docs folders are
        searched recursively (small, controlled), and common personal
        folders are searched one level deep only (bounded cost, and matches
        where a user would actually expect Almond to "just find" a file
        they reference by name).
        """
        roots = [Path(self.rag.documents_dir)]
        install_root = Path(self.base_config.data_dir).resolve().parent
        roots.append(install_root / "docs")
        home = Path.home()
        for name in ("Desktop", "Downloads", "Documents"):
            roots.append(home / name)
        return roots

    def _resolve_pdf_candidate(self, candidate: str) -> Path | None:
        candidate = candidate.strip().strip("'\"")
        if not candidate:
            return None

        direct = Path(candidate)
        if direct.is_file():
            return direct.resolve()

        wanted = candidate.casefold()

        def is_match(entry: Path) -> bool:
            if not entry.is_file():
                return False
            if _ALMOND_OUTPUT_STEM_RE.search(entry.stem):
                return False  # a previously generated branded PDF, not a source document
            stem_cf = entry.stem.casefold()
            return (
                entry.name.casefold() == wanted
                or stem_cf == wanted
                or wanted in stem_cf
                or (len(entry.stem) >= 3 and stem_cf in wanted)
            )

        found: set[Path] = set()
        for index, root in enumerate(self._pdf_search_roots()):
            if not root.is_dir():
                continue
            entries = root.rglob("*") if index < 2 else root.iterdir()
            found.update(entry.resolve() for entry in entries if is_match(entry))

        if len(found) == 1:
            return next(iter(found))
        return None

    def _perform_pdf_action(self, action: str) -> str:
        payload = action[len("PDF ") :]
        path, _, title = payload.partition("|||")
        return self._handle_pdf_command(("create", path, "--title", title)) or ""

    def _handle_pdf_command(self, args: tuple[str, ...]) -> str | None:
        if not args or args[0] == "help":
            return (
                "[b]Almond PDF[/b]\n"
                '/pdf create <file> [--title "Title"]   Generate a branded PDF\n'
                "/pdf status                            Show output settings\n"
                "/pdf help                              Show this message\n\n"
                "Supported: .txt .md .docx .pdf"
            )
        if args[0] == "status":
            return (
                f"Output directory: [#F15A24]{escape(str(self.base_config.outputs_dir))}[/]\n"
                "Supported: .txt .md .docx .pdf"
            )
        if args[0] != "create":
            raise ValueError('Usage: /pdf help|status|create <file> [--title "Title"]')

        rest = list(args[1:])
        title: str | None = None
        if "--title" in rest:
            index = rest.index("--title")
            if index + 1 >= len(rest):
                raise ValueError('Usage: /pdf create <file> --title "Title"')
            title = rest[index + 1]
            del rest[index : index + 2]
        if not rest:
            raise ValueError('Usage: /pdf create <file> [--title "Title"]')
        source = rest[0]

        try:
            result = self.core.create_pdf(source, title)
        except (DocumentError, PdfGenerationError) as exc:
            return (
                "[#A96363]PDF generation failed.[/]\n\n"
                f"Reason:\n{escape(str(exc))}\n\n"
                "Supported:\n.txt .md .docx .pdf"
            )

        return (
            "[b]Almond PDF[/b]\n\n"
            "[#6F9B74]✓[/] Document loaded\n"
            f"[#6F9B74]✓[/] {result.word_count:,} words extracted\n"
            "[#6F9B74]✓[/] Almond template applied\n"
            "[#6F9B74]✓[/] PDF generated\n"
            "[#6F9B74]✓[/] Output verified\n\n"
            f"Output:\n{escape(result.output_path)}"
        )

    @on(NavItem.Selected)
    def navigate(self, event: NavItem.Selected) -> None:
        self.show_view(event.name)

    def action_clear_console(self) -> None:
        self.query_one("#console", RichLog).clear()

    def action_clear_input(self) -> None:
        self.query_one("#composer", TextArea).clear()

    def action_close_overlay(self) -> None:
        self.query_one("#suggestions", Static).styles.display = "none"

    def action_cancel_operation(self) -> None:
        self.workers.cancel_all()
        self.query_one("#console", RichLog).write("[#9CA3A8]Current operation cancelled.[/]")

    def action_shortcuts(self) -> None:
        self.push_screen(HelpScreen())

    def action_history_previous(self) -> None:
        if self.history:
            self.history_index = max(0, self.history_index - 1)
            self.query_one("#composer", TextArea).load_text(self.history[self.history_index])

    def action_history_next(self) -> None:
        if self.history:
            self.history_index = min(len(self.history), self.history_index + 1)
            text = (
                "" if self.history_index == len(self.history) else self.history[self.history_index]
            )
            self.query_one("#composer", TextArea).load_text(text)

    def action_browse_file(self) -> None:
        self._browse_file()

    @work(exclusive=True)
    async def _browse_file(self) -> None:
        path = await asyncio.to_thread(self._pick_file_dialog)
        if not path:
            return
        editor = self.query_one("#composer", TextArea)
        editor.load_text(f'/pdf create {path.replace(chr(92), "/")} --title ""')
        editor.focus()
        self.logs.add("ui", "INFO", f"File picked: {path}")

    @staticmethod
    def _pick_file_dialog() -> str:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askopenfilename(
                title="Select a document for Almond",
                filetypes=[
                    (
                        "Supported documents",
                        "*.txt *.md *.docx *.pdf *.png *.jpg *.jpeg *.bmp *.tiff",
                    ),
                    ("All files", "*.*"),
                ],
            )
        finally:
            root.destroy()

    def action_autocomplete(self) -> None:
        editor = self.query_one("#composer", TextArea)
        matches = command_suggestions(editor.text)
        if matches:
            editor.load_text(matches[0] + (" " if matches[0].count(" ") == 0 else ""))


def run() -> None:
    AlmondDeveloperApp().run()
