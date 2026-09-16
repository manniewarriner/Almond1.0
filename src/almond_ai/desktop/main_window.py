"""MainWindow: sidebar + per-bot chat pages + Settings.

Owns no model/session logic itself -- every action here (`_send`,
`_regenerate`, `_on_create_pdf`, `_on_draft_email`) is a thin wrapper that
calls into the shared `AlmondCore` (via a worker thread) and renders the
result. The desktop app has no developer console: this module never
imports/instantiates anything from `almond_ai.ui` (the Textual terminal).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from almond_ai.bots.models import BotDefinition
from almond_ai.bots.registry import GENERAL_BOT, GENERAL_BOT_ID
from almond_ai.core import AlmondCore
from almond_ai.desktop import theme
from almond_ai.desktop.icons import bot_icon, brand_mark_pixmap, nut_pixmap
from almond_ai.desktop.widgets.calculator_dialog import CalculatorDialog
from almond_ai.desktop.widgets.chat_view import ChatView
from almond_ai.desktop.widgets.drafting_dialog import DraftingDialog
from almond_ai.desktop.widgets.settings_view import SettingsView
from almond_ai.desktop.widgets.sidebar import SETTINGS_ID, Sidebar
from almond_ai.desktop.workers import ChatStreamWorker, PdfCreateWorker
from app.pdf.service import PdfResult
from app.safety.content_filter import ContentPolicyError, enforce_safe_input

FILE_FILTER = (
    "Supported documents (*.txt *.md *.docx *.pdf *.png *.jpg *.jpeg *.bmp *.tiff);;All files (*.*)"
)

# Desktop empty-state copy per specialist bot. Distinct from
# almond_ai.app.EMPTY_STATE_BODY (the terminal's one-liner) because the
# desktop empty state has room for the fuller explanation the design spec
# calls for -- the underlying bot (instructions, tools, status) is the
# same BotDefinition either way.
_EMPTY_STATE = {
    "calculator": {
        "body": (
            "Withdrawal tax, carry forward, and annual allowance -- calculated precisely, "
            "never estimated by the model."
        ),
        "action": "Run a Calculation",
    },
    "drafting": {
        "body": "Draft professional client emails using the local model.",
        "action": "Draft Client Email",
    },
    "document": {
        "body": "Turn any local file into a branded Almond Financial PDF.",
        "action": "Create PDF",
    },
}


class MainWindow(QMainWindow):
    def __init__(self, core: AlmondCore) -> None:
        super().__init__()
        self.core = core
        self.setWindowTitle("Almond AI")
        self.resize(1440, 900)

        self._chat_views: dict[str, ChatView] = {}
        self._pages: dict[str, QWidget] = {}
        self._status_labels: list[QLabel] = []
        self._active_workers: dict[str, ChatStreamWorker] = {}
        # A failed/blocked chat turn is rolled back out of session.messages
        # (AlmondCore.stream_reply never lets a failed exchange poison
        # model context) but the desktop UI still showed it until the next
        # nav-away/back silently wiped it via render_messages(). Kept here
        # instead, purely for redisplay -- never fed back to the model.
        self._bot_notices: dict[str, tuple[str, str]] = {}
        self._pdf_worker: PdfCreateWorker | None = None
        # _regenerate() only ever inspects session.messages[-1], so only the
        # most recently created PDF message can ever still be the tail --
        # once anything else is appended after it, it's permanently
        # irrelevant to that check. Tracking just the latest one (instead of
        # accumulating every PDF message for the life of the window) keeps
        # this O(1) instead of growing without bound over a long session.
        self._last_pdf_message: dict[str, str] | None = None
        self._pdf_message: dict[str, str] | None = None
        self._closing = False
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(100)
        self._close_timer.timeout.connect(self.close)
        self._drafting_last_fields: dict[str, str] | None = None
        self._drafting_toolbar: QWidget | None = None
        self._drafting_edit_button: QPushButton | None = None
        self._calculator_toolbar: QWidget | None = None
        self._document_toolbar: QWidget | None = None
        self._document_create_button: QPushButton | None = None

        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar(core.staff_bots())
        self.sidebar.item_selected.connect(self._on_nav_selected)
        root_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)

        self._build_general_page()
        for bot in core.staff_bots():
            self._build_bot_page(bot)

        self.settings_view = SettingsView(core)
        self.stack.addWidget(self.settings_view)
        self._pages[SETTINGS_ID] = self.settings_view

        self.sidebar.set_active(GENERAL_BOT_ID)
        self.stack.setCurrentWidget(self._pages[GENERAL_BOT_ID])

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_model_status)
        self._status_timer.start(8000)
        self._refresh_model_status()

    # -- page construction --------------------------------------------------

    def _build_general_page(self) -> None:
        chat_view = ChatView(
            empty_widget=self._build_welcome_hero(),
            show_composer=False,
            composer_placeholder="Message Almond…",
        )
        chat_view.message_submitted.connect(lambda text: self._send(GENERAL_BOT_ID, text))
        chat_view.regenerate_requested.connect(lambda: self._regenerate(GENERAL_BOT_ID))
        self._chat_views[GENERAL_BOT_ID] = chat_view
        page = self._wrap_page(GENERAL_BOT.name, "Coming Soon", None, chat_view)
        self.stack.addWidget(page)
        self._pages[GENERAL_BOT_ID] = page

    def _build_welcome_hero(self) -> QWidget:
        """Centred welcome screen: brand mark, headline, three quick-start cards."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(0)
        layout.addStretch(2)

        brand_label = QLabel("Almond\nFinancial")
        brand_label.setObjectName("welcomeBrandTitle")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(brand_label)
        layout.addSpacing(12)

        mark_label = QLabel()
        mark_label.setObjectName("welcomeBrandMark")
        mark_label.setPixmap(brand_mark_pixmap(theme.ACCENT, 128, line_color="#FFFFFF"))
        mark_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(mark_label)
        layout.addSpacing(4)

        partner_label = QLabel("A Quilter partner")
        partner_label.setObjectName("welcomePartner")
        partner_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(partner_label)
        layout.addSpacing(20)

        heading_row = QHBoxLayout()
        heading_row.addStretch(1)
        heading = QLabel("How can I help today?")
        heading.setObjectName("welcomeHeading")
        heading_row.addWidget(heading)
        # General Chat's own status, not borrowed from any quick-start
        # card below -- Calculator/Drafting/Document are all shipped, so
        # nothing else in this page still carries a "Coming Soon" badge.
        badge = QLabel("Coming Soon")
        badge.setObjectName("comingSoonBadge")
        heading_row.addWidget(badge)
        heading_row.addStretch(1)
        layout.addLayout(heading_row)
        layout.addSpacing(28)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addStretch(1)
        cards.addWidget(
            self._build_quick_action_card(
                "walnut",
                theme.BOT_ACCENTS["calculator"],
                "Run a calculation",
                "UK pension tax calculators",
                on_click=lambda: self._on_nav_selected("calculator"),
            )
        )
        cards.addWidget(
            self._build_quick_action_card(
                "hazelnut",
                theme.BOT_ACCENTS["drafting"],
                "Draft an email",
                "Professional, client-ready drafts",
                on_click=lambda: self._on_nav_selected("drafting"),
            )
        )
        cards.addWidget(
            self._build_quick_action_card(
                "almond",
                theme.BOT_ACCENTS["document"],
                "Create a document",
                "Turn your ideas into branded PDFs",
                on_click=lambda: self._on_nav_selected("document"),
            )
        )
        cards.addStretch(1)
        row = QWidget()
        row.setLayout(cards)
        row.setMaximumWidth(920)
        center = QHBoxLayout()
        center.addStretch(1)
        center.addWidget(row)
        center.addStretch(1)
        layout.addLayout(center)

        layout.addStretch(3)
        return page

    def _build_quick_action_card(
        self,
        nut: str,
        color: str,
        title: str,
        subtitle: str,
        on_click=None,
        coming_soon: bool = False,
    ) -> QWidget:
        card = QPushButton()
        card.setObjectName("quickActionCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setFlat(True)
        card.setFixedHeight(132)
        card.setMinimumWidth(268)
        if on_click is not None:
            card.clicked.connect(on_click)
        else:
            card.clicked.connect(self._focus_general_composer)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        icon_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(nut_pixmap(nut, color, 44))
        icon_row.addWidget(icon_label)
        icon_row.addStretch(1)
        if coming_soon:
            badge = QLabel("Coming Soon")
            badge.setObjectName("comingSoonBadge")
            icon_row.addWidget(badge)
        layout.addLayout(icon_row)

        title_label = QLabel(title)
        title_label.setObjectName("quickActionTitle")
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("quickActionSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        return card

    def _focus_general_composer(self) -> None:
        chat_view = self._chat_views[GENERAL_BOT_ID]
        if chat_view.composer is not None:
            chat_view.composer.focus()

    def _build_bot_page(self, bot: BotDefinition) -> None:
        copy = _EMPTY_STATE.get(bot.id, {})
        chat_view = ChatView(
            empty_title=bot.name,
            empty_body=copy.get("body", "Ask anything."),
            empty_status=copy.get("status"),
            action_label=copy.get("action"),
            secondary_label=None,
            show_composer=False,
            composer_placeholder=f"Message {bot.name}…",
            toolbar=(
                self._build_drafting_toolbar()
                if bot.id == "drafting"
                else self._build_calculator_toolbar()
                if bot.id == "calculator"
                else self._build_document_toolbar()
                if bot.id == "document"
                else None
            ),
        )
        chat_view.message_submitted.connect(lambda text, b=bot.id: self._send(b, text))
        chat_view.regenerate_requested.connect(lambda b=bot.id: self._regenerate(b))
        if bot.id == "drafting":
            chat_view.primary_action_clicked.connect(self._on_draft_email)
        elif bot.id == "calculator":
            chat_view.primary_action_clicked.connect(self._on_run_calculator)
        elif bot.id == "document":
            chat_view.primary_action_clicked.connect(self._on_create_pdf)

        self._chat_views[bot.id] = chat_view
        accent = theme.BOT_ACCENTS.get(bot.id, theme.ACCENT)
        icon = bot_icon(bot.id, accent, size=32)
        page = self._wrap_page(bot.name, bot.description, icon, chat_view)
        self.stack.addWidget(page)
        self._pages[bot.id] = page

    def _wrap_page(self, title: str, subtitle: str, icon, chat_view: ChatView) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("contentHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(34, 24, 34, 24)
        header_layout.setSpacing(14)

        if icon is not None:
            icon_label = QLabel()
            icon_label.setPixmap(icon.pixmap(32, 32))
            header_layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("botTitle")
        text_col.addWidget(title_label)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("botSubtitle")
        text_col.addWidget(subtitle_label)
        header_layout.addLayout(text_col)
        header_layout.addStretch(1)

        # Placeholder text only -- overwritten by the constructor's
        # _refresh_model_status() call before the window is ever shown.
        # Keep that call after all pages (and their status labels) are
        # built, or this placeholder will flash briefly on launch.
        status = QLabel("●  Local    Private")
        status.setObjectName("statusBadge")
        header_layout.addWidget(status)
        self._status_labels.append(status)

        layout.addWidget(header)

        content_wrap = QWidget()
        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(34, 22, 34, 26)
        content_layout.addWidget(chat_view)
        layout.addWidget(content_wrap, 1)

        return page

    # -- navigation ------------------------------------------------------

    def _on_nav_selected(self, nav_id: str) -> None:
        self.sidebar.set_active(nav_id)
        self.stack.setCurrentWidget(self._pages[nav_id])
        if nav_id == SETTINGS_ID:
            return
        chat_view = self._chat_views[nav_id]
        active = self._active_workers.get(nav_id)
        # Keep the pending bubble until queued completion signals have been handled,
        # even if the native thread has already finished.
        pdf_active = nav_id == "document" and self._pdf_worker is not None
        # Bot pages are currently action-only. Keep any backend session
        # history private until chat UI returns.
        if nav_id == GENERAL_BOT_ID and active is None and not pdf_active:
            chat_view.show_empty_state(True)

    # -- chat --------------------------------------------------------------

    def _any_worker_active(self) -> bool:
        # Only one AlmondCore call (chat or PDF, for any bot) may be in
        # flight at a time -- the shared model provider/local server isn't
        # verified safe for concurrent requests, so a second bot's worker
        # starting mid-stream risks interleaved output or a provider-side
        # error surfacing as a generic failure.
        return bool(self._active_workers) or self._pdf_worker is not None

    def _warn_busy(self) -> None:
        QMessageBox.information(
            self,
            "Almond is busy",
            "Almond is still working on another response. Wait for it to finish before starting a new one.",
        )

    def _send(self, bot_id: str, text: str) -> None:
        if self._closing or (bot_id == "document" and self._pdf_worker is not None):
            return
        existing = self._active_workers.get(bot_id)
        if existing is not None:
            return
        if self._any_worker_active():
            self._warn_busy()
            return
        try:
            enforce_safe_input(text)
        except ContentPolicyError as exc:
            QMessageBox.warning(self, "Message blocked", str(exc))
            return

        chat_view = self._chat_views[bot_id]
        chat_view.add_user_message(text)
        chat_view.begin_assistant_message()
        chat_view.set_busy(True)

        self._bot_notices.pop(bot_id, None)

        worker = ChatStreamWorker(self.core, bot_id, text)
        worker.chunk_received.connect(lambda t, b=bot_id: self._on_chunk(b, t))
        worker.finished_ok.connect(
            lambda t, think, total, b=bot_id: self._on_finished(b, t, think, total)
        )
        worker.blocked.connect(lambda msg, b=bot_id, u=text: self._on_blocked(b, u, msg))
        worker.failed.connect(lambda msg, b=bot_id, u=text: self._on_failed(b, u, msg))
        worker.finished.connect(lambda b=bot_id: self._on_worker_done(b))
        self._active_workers[bot_id] = worker
        worker.start()

    def _on_chunk(self, bot_id: str, cumulative_text: str) -> None:
        if bot_id in self._chat_views:
            self._chat_views[bot_id].update_streaming_text(cumulative_text.strip())

    def _on_finished(
        self, bot_id: str, final_text: str, thinking_seconds: float, total_seconds: float
    ) -> None:
        self._bot_notices.pop(bot_id, None)
        text = final_text.strip()
        if bot_id == "drafting":
            text += (
                "\n\n⚠ Review before sending — check for any stated facts or status "
                "you didn't provide."
            )
            # AlmondCore.stream_reply already appended the unmodified
            # `final_text` as the session's assistant message; patch it in
            # place so the warning survives a nav-away/nav-back re-render
            # (ChatView.render_messages reads straight from
            # core.sessions.get(bot_id).messages) instead of only living in
            # this one-shot streaming label.
            messages = self.core.sessions.get(bot_id).messages
            if messages and messages[-1]["role"] == "assistant":
                messages[-1]["content"] = text
        chat_view = self._chat_views[bot_id]
        chat_view.update_streaming_text(text)
        chat_view.set_timing(thinking_seconds, total_seconds)
        self._refresh_model_status()

    def _on_blocked(self, bot_id: str, user_text: str, message: str) -> None:
        self._chat_views[bot_id].update_streaming_text(message)
        self._bot_notices[bot_id] = (user_text, message)

    def _on_failed(self, bot_id: str, user_text: str, message: str) -> None:
        text = f"Model connection failed.\n{message}"
        self._chat_views[bot_id].update_streaming_text(text)
        self._bot_notices[bot_id] = (user_text, text)

    def _on_worker_done(self, bot_id: str) -> None:
        self._active_workers.pop(bot_id, None)
        if bot_id in self._chat_views:
            self._chat_views[bot_id].set_busy(False)

    def _regenerate(self, bot_id: str) -> None:
        if self._closing or (bot_id == "document" and self._pdf_worker is not None):
            return
        existing = self._active_workers.get(bot_id)
        if existing is not None and existing.isRunning():
            return
        if self._any_worker_active():
            self._warn_busy()
            return
        session = self.core.sessions.get(bot_id)
        if not session.messages or session.messages[-1]["role"] != "assistant":
            return
        if session.messages[-1] is self._last_pdf_message:
            return  # A PDF result is not a model reply to regenerate.
        session.messages.pop()
        if not session.messages or session.messages[-1]["role"] != "user":
            return
        last_user = session.messages.pop()["content"]
        self._chat_views[bot_id].render_messages(session.messages)
        self._send(bot_id, last_user)

    # -- Drafting ------------------------------------------------------------

    def _build_drafting_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setVisible(False)  # shown once the first draft exists
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        new_button = QPushButton("New Draft")
        new_button.setObjectName("secondaryAction")
        new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_button.clicked.connect(self._on_draft_email)
        layout.addWidget(new_button)

        edit_button = QPushButton("Edit Last Draft")
        edit_button.setObjectName("secondaryAction")
        edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_button.clicked.connect(self._on_edit_last_draft)
        layout.addWidget(edit_button)

        layout.addStretch(1)
        self._drafting_toolbar = bar
        self._drafting_edit_button = edit_button
        return bar

    def _on_draft_email(self) -> None:
        existing = self._active_workers.get("drafting")
        if existing is not None and existing.isRunning():
            return
        result = DraftingDialog.get_prompt(self)
        if result is None:
            return
        prompt, fields = result
        self._drafting_last_fields = fields
        self._drafting_toolbar.setVisible(True)
        self._send("drafting", prompt)

    def _on_edit_last_draft(self) -> None:
        existing = self._active_workers.get("drafting")
        if existing is not None and existing.isRunning():
            return
        if self._drafting_last_fields is None:
            return
        result = DraftingDialog.get_prompt(self, initial=self._drafting_last_fields)
        if result is None:
            return
        prompt, fields = result
        self._drafting_last_fields = fields
        self._send("drafting", prompt)

    # -- Calculator ------------------------------------------------------------

    def _build_calculator_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setVisible(False)  # shown once the first calculation exists
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        new_button = QPushButton("New Calculation")
        new_button.setObjectName("secondaryAction")
        new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_button.clicked.connect(self._on_run_calculator)
        layout.addWidget(new_button)

        layout.addStretch(1)
        self._calculator_toolbar = bar
        return bar

    def _on_run_calculator(self) -> None:
        if self._closing or "calculator" in self._active_workers:
            return
        if self._any_worker_active():
            self._warn_busy()
            return
        result = CalculatorDialog.get_calculation(self, core=self.core)
        if result is None:
            return
        request_text, response_text = result
        messages = self.core.sessions.get("calculator").messages
        messages.append({"role": "user", "content": request_text})
        messages.append({"role": "assistant", "content": response_text})
        if self._calculator_toolbar is not None:
            self._calculator_toolbar.setVisible(True)

    # -- Document / PDF -----------------------------------------------------

    def _build_document_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setVisible(False)  # shown once the first PDF exists
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        create_button = QPushButton("Create PDF")
        create_button.setObjectName("secondaryAction")
        create_button.setCursor(Qt.CursorShape.PointingHandCursor)
        create_button.clicked.connect(self._on_create_pdf)
        layout.addWidget(create_button)

        layout.addStretch(1)
        self._document_toolbar = bar
        self._document_create_button = create_button
        return bar

    def _set_document_creating(self, creating: bool) -> None:
        if self._document_create_button is None:
            return
        self._document_create_button.setText("Creating PDF…" if creating else "Create PDF")
        self._document_create_button.setEnabled(not creating)

    def _show_notification(self, title: str, text: str, *, warning: bool = False) -> None:
        # A non-modal, non-blocking popup: QMessageBox's static helpers
        # (.information()/.warning()) and .exec() all block the calling
        # thread's event loop until dismissed -- fine for an interactive
        # user prompt, but fatal here since this fires from a worker's
        # completion signal with nobody guaranteed to click it (e.g. under
        # the "offscreen" Qt platform in tests, it would hang forever).
        # .show() displays the same dialog without blocking anything.
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setModal(False)
        box.show()

    def _on_create_pdf(self) -> None:
        if self._closing or self._pdf_worker is not None or "document" in self._active_workers:
            return
        if self._any_worker_active():
            self._warn_busy()
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a document for Almond", str(Path.home()), FILE_FILTER
        )
        if not path:
            return
        chat_view = self._chat_views["document"]
        request_text = f"Selected file: {Path(path).name}"
        chat_view.add_user_message(request_text)
        messages = self.core.sessions.get("document").messages
        messages.append({"role": "user", "content": request_text})
        self._pdf_message = {"role": "assistant", "content": "Preparing document…"}
        messages.append(self._pdf_message)
        self._last_pdf_message = self._pdf_message
        chat_view.begin_assistant_message(show_thinking=True)
        chat_view.set_busy(True)
        self._set_document_creating(True)
        worker = PdfCreateWorker(
            self.core,
            path,
            None,
            fast=False,
            page_range=None,
        )
        worker.progress.connect(self._on_pdf_progress)
        worker.finished_ok.connect(self._on_pdf_finished)
        worker.failed.connect(self._on_pdf_failed)
        worker.finished.connect(self._on_pdf_worker_done)
        self._pdf_worker = worker
        worker.start()

    def _on_pdf_progress(self, message: str) -> None:
        # Intermediate step updates just track the latest status text for
        # session history -- the thinking indicator (bot + ellipsis, shared
        # with Drafting/Chat) keeps animating in place of the reply text
        # until a terminal result lands via _on_pdf_finished/_on_pdf_failed.
        # Calling update_streaming_text here would swap the indicator out
        # for plain status text on the very first tick, which is what made
        # Document's "working" state look different from every other bot.
        if self._pdf_message is not None:
            self._pdf_message["content"] = message

    def _on_pdf_finished(self, result: PdfResult) -> None:
        notices = "\n".join(result.warnings)
        final_text = (
            "PDF created\n\n"
            f"{result.word_count:,} words extracted\n"
            + (f"{notices}\n\n" if notices else "")
            + "Almond template applied · Output verified\n\n"
            f"Saved to: {result.output_path}"
        )
        if self._pdf_message is not None:
            self._pdf_message["content"] = final_text
        self._chat_views["document"].update_streaming_text(final_text)
        if self._document_toolbar is not None:
            self._document_toolbar.setVisible(True)
        if not self._closing:
            self._show_notification(
                "PDF created",
                "Your Almond-branded PDF was created successfully.\n\n"
                f"Saved to:\n{result.output_path}",
            )

    def _on_pdf_failed(self, message: str) -> None:
        final_text = f"PDF generation failed\n\n{message}"
        if self._pdf_message is not None:
            self._pdf_message["content"] = final_text
        self._chat_views["document"].update_streaming_text(final_text)
        if self._document_toolbar is not None:
            self._document_toolbar.setVisible(True)
        if not self._closing:
            self._show_notification("PDF generation failed", message, warning=True)

    def _on_pdf_worker_done(self) -> None:
        self._pdf_worker = None
        self._pdf_message = None
        self._set_document_creating(False)
        self._chat_views["document"].set_busy(False)

    # -- status -----------------------------------------------------------

    def _refresh_model_status(self) -> None:
        online = self.core.model_online()
        if self.core.config.model.provider == "fake":
            text, color = "AI Mock", theme.STATUS_STARTING
        elif online:
            text, color = "Local model online", theme.STATUS_AVAILABLE
        else:
            text, color = "Local model offline", theme.STATUS_ERROR
        for label in self._status_labels:
            label.setText(f"●  {text}")
            label.setStyleSheet(
                f"color: {color}; font-size: {theme.TYPE_BODY}px; font-weight: 600;"
            )
        self.settings_view.set_model_status(text)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Keep Qt's event loop and worker references alive until all threads finish.
        # No blocking wait or forced termination: a PDF already rendering completes.
        workers = [*self._active_workers.values(), self._pdf_worker]
        if any(worker is not None and not worker.wait(0) for worker in workers):
            self._closing = True
            self._status_timer.stop()
            self.centralWidget().setEnabled(False)
            self.statusBar().showMessage("Finishing active work before closing…")
            self._close_timer.start()
            event.ignore()
            return
        self._close_timer.stop()
        self._status_timer.stop()
        self.core.stop()
        super().closeEvent(event)
