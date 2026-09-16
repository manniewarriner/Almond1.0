"""UI-level bot sidebar/session behaviour: selection, New Bot flow, status fixes."""

import asyncio

from textual.widgets import Button, Static

from almond_ai.app import AlmondDeveloperApp
from almond_ai.config import DeveloperConfig, ModelSettings
from almond_ai.ui.screens.new_bot import NewBotScreen
from almond_ai.ui.widgets.bot_sidebar import BotNavItem
from tests.conftest import wait_until_ready


def _fake_config(**kwargs) -> DeveloperConfig:
    return DeveloperConfig(model=ModelSettings(provider="fake"), **kwargs)


async def _ready_app(size=(120, 40)):
    app = AlmondDeveloperApp(_fake_config())
    pilot_cm = app.run_test(size=size)
    pilot = await pilot_cm.__aenter__()
    await pilot.pause()
    await wait_until_ready(app, pilot)
    return app, pilot, pilot_cm


def test_general_chat_is_default_and_all_built_in_bots_listed():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            assert app.sessions.active_id == "general"
            bot_ids = ("calculator", "drafting", "document", "coding")
            for bot_id in bot_ids:
                assert app.query_one(f"#bot-{bot_id}", BotNavItem)
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_inbox_manager_removed():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            assert "inbox-manager" not in app.sessions.bots
            assert not app.query("#bot-inbox-manager")
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_calculator_is_available():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            calculator = app.sessions.bots["calculator"]
            assert calculator.status == "available"
            assert calculator.unique_tool == "pension_withdrawal_tax"
            item = app.query_one("#bot-calculator", BotNavItem)
            assert "WIP" not in item.content
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_coding_is_experimental():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            coding = app.sessions.bots["coding"]
            assert coding.status == "experimental"
            assert coding.unique_tool == "local_development"
            item = app.query_one("#bot-coding", BotNavItem)
            assert "EXPERIMENTAL" in item.content
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_drafting_tool_available():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            drafting = app.sessions.bots["drafting"]
            assert drafting.status == "available"
            assert drafting.unique_tool == "draft_client_email"
            item = app.query_one("#bot-drafting", BotNavItem)
            assert "AVAILABLE" not in item.content  # available bots show no baseline badge
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_document_pdf_tool_available():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            document = app.sessions.bots["document"]
            assert document.status == "available"
            assert document.unique_tool == "document_to_pdf"
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_clicking_a_bot_switches_active_session_and_highlights_it():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            await pilot.click("#bot-calculator")
            await pilot.pause()
            assert app.sessions.active_id == "calculator"
            item = app.query_one("#bot-calculator", BotNavItem)
            assert item.has_class("nav-selected")
            general_item = app.query_one("#bot-general", BotNavItem)
            assert not general_item.has_class("nav-selected")
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_settings_reachable_and_developer_views_still_work():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            app.show_view("Settings")
            await pilot.pause()
            assert app.active_view == "Settings"
            app.show_view("Tools")
            await pilot.pause()
            assert app.active_view == "Tools"
            assert app.query_one("#view-tools").has_class("view-active")
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_tools_view_maps_specialist_bots_to_capabilities():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            app.show_view("Tools")
            await pilot.pause()
            # Card's first child is its Label title (a Static subclass) --
            # the actual body is the last Static.
            body = app.query_one("#specialist-capabilities").query(Static)[-1].content
            assert "pension_withdrawal_tax" in body
            assert "draft_client_email" in body
            assert "document_to_pdf" in body
            assert "local_development" in body
            assert "Available" in body
            assert "Experimental" in body
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_welcome_panel_hides_after_first_message_and_returns_for_empty_bot():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            panel = app.query_one("#welcome-panel")
            assert panel.styles.display != "none"
            app.messages.append({"role": "user", "content": "hi"})
            app._update_empty_state()
            assert panel.styles.display == "none"
            app.switch_bot("calculator")
            await pilot.pause()
            assert app.query_one("#welcome-panel").styles.display != "none"
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_empty_state_is_bot_specific_not_generic():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            general_text = app.query_one("#welcome-text", Static).content
            assert "How can I help" in general_text
            app.switch_bot("calculator")
            await pilot.pause()
            calculator_text = app.query_one("#welcome-text", Static).content
            assert "carry forward" in calculator_text.lower()
            assert calculator_text != general_text
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_only_the_active_bots_quick_action_is_visible():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            for bot_id in ("calculator", "drafting", "document", "coding"):
                assert app.query_one(f"#quick-action-{bot_id}").styles.display == "none"
            app.switch_bot("drafting")
            await pilot.pause()
            assert app.query_one("#quick-action-drafting").styles.display != "none"
            assert app.query_one("#quick-action-document").styles.display == "none"
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_coding_quick_action_is_disabled():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            assert app.query_one("#quick-action-coding", Button).disabled is True
            assert app.query_one("#quick-action-calculator", Button).disabled is False
            assert app.query_one("#quick-action-drafting", Button).disabled is False
            assert app.query_one("#quick-action-document", Button).disabled is False
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_drafting_quick_action_prefills_composer():
    from textual.widgets import TextArea

    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            app.switch_bot("drafting")
            await pilot.pause()
            await pilot.click("#quick-action-drafting")
            await pilot.pause()
            text = app.query_one("#composer", TextArea).text
            assert "Draft a client email" in text
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_calculator_computes_deterministically_not_via_the_model():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            app.permissions.add("calculator:use")
            output = app._command_output("tool", ("run", "pension_withdrawal_tax", "10000"))
            assert "Tax-free" in output
            assert "Net" in output
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_coding_does_not_modify_files():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            app.permissions.add("assistant:use")
            output = app._command_output("tool", ("run", "local_development"))
            assert output == "Local development agent is still in development."
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_new_bot_screen_creates_bot_definition():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            screen = NewBotScreen(frozenset(app.sessions.bots.keys()))
            app.push_screen(screen, callback=app._on_new_bot_created)
            await pilot.pause()
            screen.query_one("#bot-name").value = "Portfolio Analyst"
            screen.query_one("#bot-description").value = "Analyses portfolios"
            screen.query_one("#bot-instructions").text = "Be precise and cite sources."
            screen.create()
            await pilot.pause()
            assert "portfolio-analyst" in app.sessions.bots
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_new_bot_tools_are_allowlisted_only():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            screen = NewBotScreen(frozenset(app.sessions.bots.keys()))
            app.push_screen(screen, callback=app._on_new_bot_created)
            await pilot.pause()
            screen.query_one("#bot-name").value = "Safe Bot"
            screen.query_one("#bot-tool-calculator").value = True
            screen.create()
            await pilot.pause()
            bot = app.sessions.bots["safe-bot"]
            assert bot.tools == ["calculator"]
            assert not any(word in bot.tools for word in ("shell", "sql", "email_send"))
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_new_bot_screen_rejects_empty_name():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            screen = NewBotScreen(frozenset(app.sessions.bots.keys()))
            app.push_screen(screen)
            await pilot.pause()
            screen.create()
            await pilot.pause()
            assert "required" in screen.query_one("#new-bot-error", Static).content
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_offline_status_label_is_accurate_not_ai_ready():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            app.ready = True

            class _NeverReady:
                def is_ready(self):
                    return False

            app.provider.is_ready = _NeverReady().is_ready
            app.config.model.provider = "llama_cpp"
            app._update_status()
            text = app.query_one("#system-status", Static).content
            assert "AI Offline" in text
            assert "AI Ready" not in text
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_starting_status_shown_before_ready():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.ready = False
            app.provider.is_ready = lambda: False
            app.config.model.provider = "llama_cpp"
            app._update_status()
            text = app.query_one("#system-status", Static).content
            assert "AI Starting" in text

    asyncio.run(exercise())


def test_failed_chat_does_not_poison_bot_history(monkeypatch):
    from almond_ai.models.provider import ModelProviderError

    async def exercise():
        app, pilot, cm = await _ready_app()
        try:

            async def failing_stream(_messages):
                raise ModelProviderError("boom")
                yield ""  # pragma: no cover - never reached, makes this an async generator

            monkeypatch.setattr(app.provider, "stream", failing_stream)
            app.run_chat("this will fail")
            await app.workers.wait_for_complete()
            assert app.messages == []
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_safety_filter_blocks_nsfw_chat_prompt():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            app.run_chat("adult content please")
            await app.workers.wait_for_complete()
            assert app.messages == []
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_pdf_command_still_routes_through_document_to_pdf(tmp_path):
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            source = tmp_path / "note.txt"
            source.write_text("hello world", encoding="utf-8")
            app.permissions.add("documents:read")
            output = app._handle_pdf_command(("create", str(source)))
            assert "Output:" in output
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_rag_search_still_works_via_command_output():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            output = app._command_output("rag", ("search", "anything"))
            assert output is not None
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())


def test_no_missing_stylesheet_or_widget_ids():
    async def exercise():
        app, pilot, cm = await _ready_app()
        try:
            for widget_id in (
                "#console",
                "#composer",
                "#welcome-panel",
                "#welcome-text",
                "#system-status",
                "#navigation",
                "#stream-indicator",
                "#input-label",
                "#secure-footer",
                "#quick-action-calculator",
                "#quick-action-drafting",
                "#quick-action-document",
                "#quick-action-coding",
            ):
                assert app.query_one(widget_id)
        finally:
            await cm.__aexit__(None, None, None)

    asyncio.run(exercise())
