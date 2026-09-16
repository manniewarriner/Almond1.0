"""Dedicated center-column views for each navigation destination."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, RichLog, Static

from almond_ai import __version__
from almond_ai.ui.widgets.cards import Card
from almond_ai.ui.widgets.console import ConsoleOutput
from almond_ai.ui.widgets.sidebar import NavItem

# Technical/engineering views tucked under Settings > Developer instead of
# cluttering the main sidebar. Still reachable unchanged via slash commands
# and `almond ctl` regardless of this list.
DEVELOPER_VIEW_NAMES = (
    "Agents",
    "Tools",
    "Data & RAG",
    "Integrations",
    "Evaluation",
    "Logs",
    "Deploy",
)


class ConsoleView(Vertical):
    """Chat area. The empty state is bot-specific -- see
    `AlmondDeveloperApp._update_empty_state`, which rewrites `#welcome-text`
    and shows at most one quick-action button, matching whichever bot is
    active. All four quick-action buttons are mounted up front and hidden
    via CSS (`.quick-action { display: none }`) rather than recomposed per
    switch, matching how every other view in this app is toggled.
    """

    def __init__(self) -> None:
        super().__init__(id="view-chat", classes="view view-active")

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome-panel"):
            yield Static(id="welcome-text", markup=True)
            yield Button(
                "Run a Calculation",
                id="quick-action-calculator",
                classes="quick-action",
            )
            yield Button("Draft Client Email", id="quick-action-drafting", classes="quick-action")
            yield Button("Create PDF", id="quick-action-document", classes="quick-action")
            yield Button(
                "Local Development — Experimental",
                id="quick-action-coding",
                classes="quick-action",
                disabled=True,
            )
        yield ConsoleOutput()


class AgentsView(VerticalScroll):
    def __init__(self, agents) -> None:
        super().__init__(id="view-agents", classes="view")
        self.agents = agents

    def compose(self) -> ComposeResult:
        yield Static("Available Agents", classes="view-title")
        yield Static("Purpose-built assistants with scoped access.", classes="view-subtitle")
        with Container(classes="card-grid"):
            for index, agent in enumerate(self.agents):
                tools = 4 + (index % 3)
                yield Card(
                    agent.name,
                    Static(
                        f"{escape(agent.description)}\n\n[#6F9B74]● online[/]    "
                        f"[#9CA3A8]Tools: {tools}[/]",
                        markup=True,
                    ),
                    classes="agent-card",
                )


STATUS_LABELS = {"available": "Available", "wip": "Coming Soon", "experimental": "Experimental"}


class ToolsView(Vertical):
    def __init__(self, tools, specialist_bots=()) -> None:
        super().__init__(id="view-tools", classes="view")
        self.tools = tools
        self.specialist_bots = [bot for bot in specialist_bots if bot.unique_tool]

    def compose(self) -> ComposeResult:
        yield Static("Tools", classes="view-title")
        yield Static(
            "Allow-listed capabilities and permission boundaries.", classes="view-subtitle"
        )
        if self.specialist_bots:
            lines = []
            for bot in self.specialist_bots:
                label = STATUS_LABELS.get(bot.status, bot.status.title())
                lines.append(
                    f"[{bot.accent}]{bot.icon} {escape(bot.name)}[/]\n"
                    f"  {escape(bot.unique_tool)}\n"
                    f"  [#9CA3A8]Status: {escape(label)}[/]"
                )
            yield Card(
                "Specialist Capabilities",
                Static("\n\n".join(lines), markup=True),
                id="specialist-capabilities",
            )
        yield DataTable(id="tools-table", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Name", "Mode", "Status", "Permission", "Last run")
        for tool in self.tools:
            table.add_row(
                tool.name,
                "READ" if tool.read_only else "WRITE",
                "enabled" if tool.enabled else "disabled",
                tool.required_permission.replace(":", "."),
                tool.last_status,
            )


class PermissionsView(VerticalScroll):
    """Read-only summary of what this Almond instance can currently touch."""

    def __init__(
        self,
        granted_permissions,
        tools,
        *,
        user_id: str,
        role: str,
        documents_dir,
        outputs_dir,
        data_dir,
        control_enabled: bool,
    ) -> None:
        super().__init__(id="view-permissions", classes="view")
        self.granted_permissions = sorted(granted_permissions)
        self.tools = tools
        self.user_id = user_id
        self.role = role
        self.documents_dir = documents_dir
        self.outputs_dir = outputs_dir
        self.data_dir = data_dir
        self.control_enabled = control_enabled

    def compose(self) -> ComposeResult:
        yield Static("Permissions", classes="view-title")
        yield Static(
            "What Almond is currently allowed to touch on this machine. "
            "View-only -- change grants in data/users.json.",
            classes="view-subtitle",
        )

        granted = (
            ", ".join(self.granted_permissions) if self.granted_permissions else "(none granted)"
        )
        yield Card(
            "Current identity",
            Static(
                f"[#9CA3A8]User[/]        {escape(self.user_id)}\n"
                f"[#9CA3A8]Role[/]        {escape(self.role)}\n"
                f"[#9CA3A8]Granted[/]     {escape(granted)}",
                markup=True,
            ),
        )

        yield Card(
            "Filesystem access",
            Static(
                f"[#9CA3A8]Read/index root (RAG)[/]     {escape(str(self.documents_dir))}\n"
                f"[#9CA3A8]PDF output folder[/]         {escape(str(self.outputs_dir))}\n"
                f"[#9CA3A8]App data folder[/]            {escape(str(self.data_dir))}\n\n"
                "[#9CA3A8]Note[/]  /pdf create can read any file path you give it -- "
                "it is not restricted to the folder above. RAG add/remove/reindex "
                "only ever touch files already inside the read/index root. Nothing "
                "outside the PDF output folder is ever written to.",
                markup=True,
            ),
        )

        bridge_tone = "#6F9B74" if self.control_enabled else "#9CA3A8"
        bridge_text = (
            "● Developer control bridge: ENABLED"
            if self.control_enabled
            else "○ Developer control bridge: disabled"
        )
        yield Card(
            "Network & remote access",
            Static(
                "[#6F9B74]● No outbound network calls[/] from any tool or the local "
                "model.\n"
                f"[{bridge_tone}]{bridge_text}[/]"
                " -- loopback (127.0.0.1) only, random per-instance token, never reaches "
                "the network.",
                markup=True,
            ),
        )

        yield Static("Tools", classes="view-title", id="permissions-tools-title")
        yield DataTable(id="permissions-tools-table", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#permissions-tools-table", DataTable)
        table.add_columns(
            "Tool", "Mode", "Status", "Requires permission", "You have it?", "Approval"
        )
        for tool in self.tools:
            have_it = tool.required_permission in self.granted_permissions
            table.add_row(
                tool.name,
                "READ" if tool.read_only else "WRITE",
                "enabled" if tool.enabled else "disabled",
                tool.required_permission,
                "yes" if have_it else "no",
                "asks CONFIRM" if tool.approval_required else "runs immediately",
            )


class RAGView(VerticalScroll):
    def __init__(self, status, activities: list[str] | None = None) -> None:
        super().__init__(id="view-data-rag", classes="view")
        self.rag_status = status
        self.activities = activities or []

    def compose(self) -> ComposeResult:
        yield Static("Data & RAG", classes="view-title")
        yield Static("Local retrieval health and indexing activity.", classes="view-subtitle")
        with Container(classes="metric-grid"):
            values = (
                ("RAG Status", self.rag_status.indexing, "rag-status"),
                ("Documents", str(self.rag_status.documents), "rag-documents"),
                ("Chunks", str(self.rag_status.chunks), "rag-chunks"),
                ("Embedding Model", self.rag_status.embedding_model, "rag-embedding"),
                ("Last Index", self.rag_status.last_index, "rag-last-index"),
                ("Vector Store", self.rag_status.database, "rag-vector-store"),
            )
            for title, value, metric_id in values:
                yield Card(
                    title,
                    Static(escape(value), id=metric_id, classes="metric-value"),
                    classes="metric-card",
                )
        activity = "\n".join(self.activities[-6:]) or "No indexing activity recorded."
        yield Card("Recent indexing activity", Static(activity, classes="secondary"))


class IntegrationsView(VerticalScroll):
    def __init__(self, integrations) -> None:
        super().__init__(id="view-integrations", classes="view")
        self.integrations = integrations

    def compose(self) -> ComposeResult:
        yield Static("Integrations", classes="view-title")
        yield Static("Verified local connections and optional services.", classes="view-subtitle")
        for item in self.integrations:
            online = item.status == "online"
            tone = "#6F9B74" if online else "#9CA3A8"
            latency = f"{item.latency_ms} ms" if item.latency_ms is not None else "Not measured"
            yield Card(
                item.name.title(),
                Static(
                    f"[{tone}]● {escape(item.status)}[/]    "
                    f"[#9CA3A8]{escape(item.permissions)} · {latency}[/]",
                    markup=True,
                ),
                classes="integration-card",
            )


class EvaluationView(VerticalScroll):
    def __init__(self, suites) -> None:
        super().__init__(id="view-evaluation", classes="view")
        self.suites = suites

    def compose(self) -> ComposeResult:
        yield Static("Evaluation", classes="view-title")
        yield Static(
            "Quality gates remain local until datasets become available.", classes="view-subtitle"
        )
        for suite in self.suites:
            yield Card(
                suite.name,
                Static(
                    f"[#9CA3A8]Category[/]  {suite.category}\n"
                    f"[#9CA3A8]Last run[/]  Never\n"
                    f"[#9CA3A8]Result[/]    {suite.status}",
                    markup=True,
                    id=f"eval-result-{suite.name}",
                ),
                classes="evaluation-card",
            )


class LogsView(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("Logs", classes="view-title")
        yield Static(
            "Filtered runtime events. Sensitive values stay redacted.", classes="view-subtitle"
        )
        yield RichLog(id="logs-console", markup=True, wrap=True, highlight=False)


class DeployView(VerticalScroll):
    def __init__(self, config) -> None:
        super().__init__(id="view-deploy", classes="view")
        self.config = config

    def compose(self) -> ComposeResult:
        yield Static("Deploy", classes="view-title")
        yield Static(
            "Protected release controls require explicit confirmation.", classes="view-subtitle"
        )
        yield Card(
            "Deployment status",
            Static(
                f"[#9CA3A8]Environment[/]       development\n"
                f"[#9CA3A8]Version[/]           {__version__}\n"
                "[#9CA3A8]Git commit[/]        unavailable\n"
                f"[#9CA3A8]Model[/]             {escape(self.config.model.model)}\n"
                "[#9CA3A8]Status[/]            DEV / MOCK",
                markup=True,
            ),
        )
        yield Card(
            "Production controls",
            Static(
                "Deployment and rollback remain guarded.\n"
                "Use /deploy production or /rollback, then confirm explicitly.",
                classes="secondary",
            ),
            classes="warning-card",
        )


class SettingsView(VerticalScroll):
    def __init__(self, config) -> None:
        super().__init__(id="view-settings", classes="view")
        self.config = config

    def compose(self) -> ComposeResult:
        yield Static("Settings", classes="view-title")
        yield Static(
            "Safe configuration summary. Credentials remain hidden.", classes="view-subtitle"
        )
        yield Card(
            "General",
            Static(
                f"[#9CA3A8]{'Role':<18}[/] {escape(self.config.role)}\n"
                f"[#9CA3A8]{'Log Level':<18}[/] {escape(self.config.log_level)}",
                markup=True,
            ),
        )
        yield Card("Status", Static(id="system-status", markup=True))
        yield Card(
            "Model",
            Static(
                f"[#9CA3A8]{'Provider':<18}[/] {escape(self.config.model.provider)}\n"
                f"[#9CA3A8]{'Model':<18}[/] {escape(self.config.model.model)}\n"
                f"[#9CA3A8]{'Base URL':<18}[/] {escape(str(self.config.model.base_url))}\n"
                f"[#9CA3A8]{'Temperature':<18}[/] {escape(str(self.config.model.temperature))}\n"
                f"[#9CA3A8]{'Context Window':<18}[/] "
                f"{escape(str(self.config.model.context_window))}\n"
                f"[#9CA3A8]{'Streaming':<18}[/] "
                f"{'enabled' if self.config.streaming else 'disabled'}",
                markup=True,
            ),
        )
        yield Card(
            "Privacy",
            Static(
                "[#6F9B74]● Local-only[/] -- no outbound network calls from any tool "
                f"or the local model.\n[#9CA3A8]{'RAG Top-K':<18}[/] {self.config.rag_top_k}",
                markup=True,
            ),
        )
        yield NavItem("Permissions")
        yield Label("Developer", id="settings-developer-label")
        for name in DEVELOPER_VIEW_NAMES:
            yield NavItem(name).add_class("developer-nav-item")
