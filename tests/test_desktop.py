"""Tests for the Qt desktop app (almond_ai.desktop).

Runs against the "offscreen" Qt platform (no real display needed) and the
fake model provider (no real Qwen inference). Every test drives the real
`AlmondCore` backend the terminal also uses -- these are not UI-only
smoke tests.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from almond_ai.config import DeveloperConfig, ModelSettings
from almond_ai.core import AlmondCore
from almond_ai.desktop.main_window import MainWindow
from almond_ai.desktop.widgets.drafting_dialog import DraftingDialog
from almond_ai.desktop.widgets.pdf_options_dialog import PdfOptionsDialog
from almond_ai.desktop.widgets.settings_view import SettingsView
from almond_ai.desktop.widgets.sidebar import SETTINGS_ID


def _fake_config() -> DeveloperConfig:
    return DeveloperConfig(model=ModelSettings(provider="fake"))


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window():
    core = AlmondCore(_fake_config())
    win = MainWindow(core)
    yield win
    win.close()


def _run_worker_to_completion(worker, timeout_ms: int = 10000) -> None:
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    loop.exec()


def test_desktop_app_starts_with_staff_bots_only(window):
    assert set(window._pages) == {"general", "calculator", "drafting", "document", SETTINGS_ID}
    assert "coding" not in window._pages


def test_desktop_and_core_share_one_provider(window):
    # MainWindow has no provider of its own -- everything routes through core.
    assert not hasattr(window, "provider")


def test_welcome_brand_mark_sits_directly_above_partner_line(window, qapp):
    page = window._chat_views["general"]._empty_page
    mark = page.findChild(QLabel, "welcomeBrandMark")
    partner = page.findChild(QLabel, "welcomePartner")

    assert mark is not None
    assert partner is not None

    window.show()
    qapp.processEvents()
    assert mark.geometry().bottom() < partner.geometry().top()
    assert partner.geometry().top() - mark.geometry().bottom() <= 8


def test_general_chat_is_marked_coming_soon(window):
    # Deliberate product decision: General Chat hasn't been tackled yet, so
    # it carries its own "Coming Soon" badge, in both the sidebar row and
    # the welcome-hero heading.
    sidebar_labels = window.sidebar._rows["general"].findChildren(QLabel)
    welcome_labels = window._chat_views["general"]._empty_page.findChildren(QLabel)

    assert "Coming Soon" in {label.text() for label in sidebar_labels}
    assert "Coming Soon" in {label.text() for label in welcome_labels}


def test_privacy_summary_reflects_model_endpoint(qapp):
    local_core = AlmondCore(_fake_config())
    local_view = SettingsView(local_core)
    assert "No chat data leaves" in local_view._privacy_value.text()

    remote_config = DeveloperConfig(
        model=ModelSettings(
            provider="openai_compatible",
            base_url="https://models.example.test/v1",
        )
    )
    remote_core = AlmondCore(remote_config)
    remote_view = SettingsView(remote_core)
    assert "may leave this machine" in remote_view._privacy_value.text()


def test_no_developer_console_exposed(window):
    # The desktop app must never import/build anything from the Textual
    # developer console (Agents/Tools/Data & RAG/Integrations/Evaluation/
    # Logs/Deploy views, or the control bridge).
    import almond_ai.desktop.main_window as main_window_module

    forbidden = {
        "AgentsView",
        "ToolsView",
        "RAGView",
        "IntegrationsView",
        "EvaluationView",
        "LogsView",
        "DeployView",
        "ControlServer",
        "ApplicationDispatcher",
    }
    names = set(dir(main_window_module))
    assert not (names & forbidden)
    assert set(window.sidebar._rows) == {
        "general",
        "calculator",
        "drafting",
        "document",
        SETTINGS_ID,
    }


def test_general_chat_sends_and_streams_a_reply(window):
    window._send("general", "Hello Almond")
    assert window._active_workers.get("general") is not None
    _run_worker_to_completion(window._active_workers["general"])

    session = window.core.sessions.get("general")
    assert session.messages[0] == {"role": "user", "content": "Hello Almond"}
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[1]["content"].strip()


def test_bot_switching_preserves_independent_history(window):
    window._send("general", "hello general")
    _run_worker_to_completion(window._active_workers["general"])
    window._send("drafting", "hello drafting")
    _run_worker_to_completion(window._active_workers["drafting"])

    window._on_nav_selected("calculator")
    assert window.core.sessions.get("calculator").messages == []
    window._on_nav_selected("general")
    assert len(window.core.sessions.get("general").messages) == 2
    window._on_nav_selected("drafting")
    assert len(window.core.sessions.get("drafting").messages) == 2


def test_calculator_bot_is_available_and_computes_deterministically(window, monkeypatch):
    from almond_ai.desktop.widgets.calculator_dialog import CalculatorDialog

    calculator_bot = window.core.sessions.bots["calculator"]
    assert calculator_bot.status == "available"
    assert "calculator" in window.sidebar._rows

    monkeypatch.setattr(
        CalculatorDialog,
        "get_calculation",
        staticmethod(
            lambda parent=None, core=None: ("Withdrawal tax on £10,000", "Net amount: £8,500.00")
        ),
    )
    window._on_run_calculator()

    session = window.core.sessions.get("calculator")
    assert session.messages[0] == {"role": "user", "content": "Withdrawal tax on £10,000"}
    assert session.messages[1] == {"role": "assistant", "content": "Net amount: £8,500.00"}
    # The result never went through the model -- no worker was ever started.
    assert "calculator" not in window._active_workers


def test_drafting_action_drafts_only_never_sends(window, monkeypatch):
    canned_prompt = "Draft a client email.\nPurpose: test"
    canned_fields = {"purpose": "test", "client_context": "", "key_points": "", "tone": ""}
    monkeypatch.setattr(
        DraftingDialog,
        "get_prompt",
        staticmethod(lambda parent=None, initial=None: (canned_prompt, canned_fields)),
    )
    assert not hasattr(DraftingDialog, "send")

    window._on_draft_email()
    assert window._active_workers.get("drafting") is not None
    _run_worker_to_completion(window._active_workers["drafting"])

    session = window.core.sessions.get("drafting")
    assert session.messages[0]["content"].startswith("Draft a client email.")
    assert session.messages[1]["role"] == "assistant"
    # bot instructions (shared with the terminal) must forbid sending
    assert "never send" in window.core.sessions.bots["drafting"].instructions.lower()


def test_edit_last_draft_reopens_dialog_prefilled_with_previous_fields(window, monkeypatch):
    first_fields = {"purpose": "first", "client_context": "", "key_points": "", "tone": ""}
    monkeypatch.setattr(
        DraftingDialog,
        "get_prompt",
        staticmethod(
            lambda parent=None, initial=None: (
                "Draft a client email.\nPurpose: first",
                first_fields,
            )
        ),
    )
    # isHidden() (not isVisible()) since this fixture never shows the window
    assert window._drafting_toolbar.isHidden() is True

    window._on_draft_email()
    _run_worker_to_completion(window._active_workers["drafting"])
    assert window._drafting_toolbar.isHidden() is False

    seen_initial = {}

    def _fake_get_prompt(parent=None, initial=None):
        seen_initial.update(initial or {})
        return "Draft a client email.\nPurpose: revised", {**first_fields, "purpose": "revised"}

    monkeypatch.setattr(DraftingDialog, "get_prompt", staticmethod(_fake_get_prompt))
    window._on_edit_last_draft()
    _run_worker_to_completion(window._active_workers["drafting"])

    assert seen_initial == first_fields
    session = window.core.sessions.get("drafting")
    assert session.messages[2]["content"] == "Draft a client email.\nPurpose: revised"


def test_document_bot_creates_pdf_via_shared_backend(window, tmp_path):
    window.core.base_config.outputs_dir = tmp_path / "outputs"
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.\n\nSecond paragraph.", encoding="utf-8")

    from almond_ai.desktop.workers import PdfCreateWorker

    worker = PdfCreateWorker(window.core, str(source), None)
    worker.finished_ok.connect(window._on_pdf_finished)
    worker.failed.connect(window._on_pdf_failed)
    window._pdf_worker = worker
    worker.start()
    _run_worker_to_completion(worker)

    assert (tmp_path / "outputs" / "notes-almond.pdf").is_file()


def test_pdf_options_default_to_fast_entire_document(qapp, tmp_path):
    source = tmp_path / "report.pdf"
    dialog = PdfOptionsDialog(str(source))

    assert dialog.options().fast is True
    assert dialog.options().page_range is None
    assert dialog.range_widget.isHidden()
    assert dialog.range_label.isHidden()


def test_pdf_options_support_custom_page_range(qapp, tmp_path):
    source = tmp_path / "report.pdf"
    dialog = PdfOptionsDialog(str(source))
    dialog.scope.setCurrentIndex(dialog.scope.findData("custom"))
    dialog.start_page.setValue(10)
    dialog.end_page.setValue(20)

    assert dialog.options().page_range == (10, 20)
    assert not dialog.range_widget.isHidden()
    assert not dialog.range_label.isHidden()


def test_pdf_worker_emits_progress(window, tmp_path):
    window.core.base_config.outputs_dir = tmp_path / "outputs"
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.", encoding="utf-8")

    from almond_ai.desktop.workers import PdfCreateWorker

    progress = []
    worker = PdfCreateWorker(window.core, str(source), None, fast=True)
    worker.progress.connect(progress.append)
    worker.start()
    _run_worker_to_completion(worker)

    assert "Reading document…" in progress
    assert "Rendering streaming PDF…" in progress
    assert "Verifying output…" in progress


def test_no_email_sending_capability_anywhere_in_desktop_package():
    import inspect

    import almond_ai.desktop.main_window as main_window_module
    import almond_ai.desktop.widgets.drafting_dialog as drafting_module
    import almond_ai.desktop.workers as workers_module

    modules = (main_window_module, drafting_module, workers_module)
    source = "".join(inspect.getsource(module) for module in modules)
    for forbidden in ("smtplib", "sendmail", "send_message(", "send_email("):
        assert forbidden not in source


def test_safety_filter_blocks_nsfw_prompt_before_it_reaches_the_model(window, monkeypatch):
    warnings = []

    def _fake_warning(*args, **kwargs):
        warnings.append(args)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", _fake_warning)

    window._send("general", "adult content please")

    assert warnings, "expected the safety filter to block the message"
    assert window.core.sessions.get("general").messages == []
    assert window._active_workers.get("general") is None


def test_model_offline_status_is_reported_accurately(window):
    class _OfflineProvider:
        name = "llama_cpp"

        def is_ready(self):
            return False

    window.core.provider = _OfflineProvider()
    window.core.config.model.provider = "llama_cpp"
    window._refresh_model_status()
    assert "offline" in window.settings_view._model_value.text().lower()


def test_gui_stays_responsive_while_a_chat_turn_is_in_flight(window, monkeypatch):
    """Simulates a slow model response and proves the GUI thread never blocks."""

    class _SlowProvider:
        name = "slow"

        async def stream(self, messages):
            for word in ["Working", "on", "it..."]:
                await asyncio.sleep(0.05)
                yield word + " "

    window.core.provider = _SlowProvider()
    window._send("general", "Take your time")
    worker = window._active_workers.get("general")
    assert worker is not None and worker.isRunning()

    # If the GUI thread were blocked, this navigation call (pure Qt/Python,
    # no I/O) would never return until the worker finished.
    window._on_nav_selected("document")
    assert window.stack.currentWidget() is window._pages["document"]

    _run_worker_to_completion(worker)


def test_permission_boundary_preserved_for_document_bot(window, tmp_path):
    window.core.permissions.discard("documents:read")
    window.core.base_config.outputs_dir = tmp_path / "outputs"
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.", encoding="utf-8")

    with pytest.raises(PermissionError):
        window.core.create_pdf(str(source))


def test_pdf_result_survives_navigation_and_is_not_regenerated(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from almond_ai.desktop.widgets.pdf_options_dialog import PdfOptions

    source = tmp_path / "synthetic.txt"
    source.write_text("Synthetic report", encoding="utf-8")
    window.core.base_config.outputs_dir = tmp_path / "outputs"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    monkeypatch.setattr(PdfOptionsDialog, "get_options", lambda *args: PdfOptions(True, None))
    window._on_create_pdf()
    worker = window._pdf_worker
    window._on_nav_selected("general")
    window._on_nav_selected("document")
    _run_worker_to_completion(worker)
    window._on_nav_selected("general")
    window._on_nav_selected("document")
    messages = window.core.sessions.get("document").messages
    assert len(messages) == 2
    assert "Saved to:" in messages[-1]["content"]
    labels = window._chat_views["document"].findChildren(QLabel, "assistantText")
    assert any("Saved to:" in label.text() for label in labels)
    window._regenerate("document")
    assert len(messages) == 2
    assert "document" not in window._active_workers


def test_pdf_failure_and_scope_notices_are_retained(window, monkeypatch):
    from app.pdf.service import PdfResult

    message = {"role": "assistant", "content": "Preparing"}
    window.core.sessions.get("document").messages.append(message)
    window._pdf_message = message
    window._on_pdf_finished(
        PdfResult(
            source_path="synthetic.pdf",
            output_path="excerpt.pdf",
            pages=1,
            word_count=10,
            success=True,
            warnings=["Included source pages 2–3 of 10."],
        )
    )
    assert "Included source pages 2–3 of 10." in message["content"]
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    window._on_pdf_failed("Synthetic failure")
    window._on_nav_selected("general")
    window._on_nav_selected("document")
    assert "Synthetic failure" in message["content"]


def test_close_waits_for_pdf_without_blocking_gui(window, monkeypatch, qapp):
    from threading import Event

    from almond_ai.desktop.workers import PdfCreateWorker
    from app.errors import DocumentError

    entered, release = Event(), Event()
    stopped = []

    def slow_pdf(*args, **kwargs):
        entered.set()
        release.wait(5)
        raise DocumentError("Test operation finished")

    monkeypatch.setattr(window.core, "create_pdf", slow_pdf)
    monkeypatch.setattr(window.core, "stop", lambda: stopped.append(True))
    worker = PdfCreateWorker(window.core, "synthetic.pdf", None)
    worker.finished.connect(window._on_pdf_worker_done)
    window._pdf_worker = worker
    window.show()
    worker.start()
    try:
        assert entered.wait(2)
        assert window.close() is False
        assert window.isVisible()
        assert not stopped
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        qapp.processEvents()
        assert ticks  # Qt is still processing events during shutdown.
    finally:
        release.set()
        assert worker.wait(3000)
        qapp.processEvents()
        window.close()
    assert stopped


def test_close_waits_for_chat_worker(window, monkeypatch):
    from PySide6.QtGui import QCloseEvent

    class SlowProvider:
        async def stream(self, messages):
            await asyncio.sleep(0.1)
            yield "Finished"

    window.core.provider = SlowProvider()
    stopped = []
    monkeypatch.setattr(window.core, "stop", lambda: stopped.append(True))
    window._send("general", "Synthetic prompt")
    worker = window._active_workers["general"]
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert not stopped
    _run_worker_to_completion(worker)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert stopped
