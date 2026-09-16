"""Bot/session model: independent histories, shared provider, persistence."""

import asyncio

from almond_ai.app import AlmondDeveloperApp
from almond_ai.bots.models import BotDefinition
from almond_ai.bots.registry import BUILT_IN_BOTS, GENERAL_BOT, GENERAL_BOT_ID, bot_system_prompt
from almond_ai.bots.sessions import SessionManager
from almond_ai.bots.storage import load_user_bots, save_user_bots, slugify
from almond_ai.config import DeveloperConfig, ModelSettings


def _fake_config(**kwargs) -> DeveloperConfig:
    return DeveloperConfig(model=ModelSettings(provider="fake"), **kwargs)


def _manager() -> SessionManager:
    return SessionManager([GENERAL_BOT, *BUILT_IN_BOTS])


def test_general_chat_is_the_default_session():
    manager = _manager()
    assert manager.active_id == GENERAL_BOT_ID
    assert manager.active().bot_id == GENERAL_BOT_ID


def test_switching_bots_gives_independent_histories():
    manager = _manager()
    manager.switch("calculator")
    manager.active().messages.append({"role": "user", "content": "hello calculator"})
    manager.switch("drafting")
    assert manager.active().messages == []
    manager.switch("calculator")
    assert manager.active().messages == [{"role": "user", "content": "hello calculator"}]


def test_switching_bots_does_not_reset_another_bots_session():
    manager = _manager()
    manager.switch("calculator")
    manager.active().pending_confirmation = ("RAG reindex", "CONFIRM")
    manager.switch("drafting")
    manager.switch("calculator")
    assert manager.active().pending_confirmation == ("RAG reindex", "CONFIRM")


def test_bots_have_independent_pending_confirmations():
    manager = _manager()
    manager.switch("calculator")
    manager.active().pending_confirmation = ("RAG reindex", "CONFIRM")
    manager.switch("drafting")
    assert manager.active().pending_confirmation is None


def test_bot_system_prompt_falls_back_for_general_chat():
    manager = _manager()
    general = manager.bots[GENERAL_BOT_ID]
    assert bot_system_prompt(general, "FALLBACK") == "FALLBACK"


def test_bot_system_prompt_uses_bot_instructions():
    manager = _manager()
    calculator = manager.bots["calculator"]
    prompt = bot_system_prompt(calculator, "FALLBACK")
    assert "FALLBACK" not in prompt
    assert "Active bot: Calculator" in prompt


def test_slugify_avoids_collisions():
    taken = frozenset({"calculator", "calculator-2"})
    assert slugify("Calculator", taken=taken) == "calculator-3"
    assert slugify("Brand New Bot", taken=taken) == "brand-new-bot"


def test_bot_storage_round_trips(tmp_path):
    path = tmp_path / "bots.json"
    bots = [
        BotDefinition(
            id="custom",
            name="Custom",
            description="desc",
            instructions="be custom",
            tools=["calculator"],
            rag_enabled=True,
            icon="◆",
            accent="#123456",
        )
    ]
    save_user_bots(path, bots)
    loaded = load_user_bots(path)
    assert len(loaded) == 1
    assert loaded[0].name == "Custom"
    assert loaded[0].rag_enabled is True


def test_bot_storage_missing_file_returns_empty(tmp_path):
    assert load_user_bots(tmp_path / "missing.json") == []


def test_app_sessions_share_one_provider_instance():
    app = AlmondDeveloperApp(_fake_config())
    provider_before = app.provider
    app.sessions.switch("calculator")
    app.sessions.switch("drafting")
    app.sessions.switch(GENERAL_BOT_ID)
    # Every bot session is backed by the same provider -- no per-bot model.
    assert app.provider is provider_before


def test_switch_bot_updates_active_id_and_messages_property():
    app = AlmondDeveloperApp(_fake_config())
    app.messages.append({"role": "user", "content": "general message"})
    app.sessions.switch("coding")
    assert app.messages == []
    app.sessions.switch(GENERAL_BOT_ID)
    assert app.messages == [{"role": "user", "content": "general message"}]


def test_pending_confirmation_property_scoped_to_active_bot():
    app = AlmondDeveloperApp(_fake_config())
    app.pending_confirmation = ("RAG add doc.txt", "CONFIRM")
    app.sessions.switch("document")
    assert app.pending_confirmation is None
    app.sessions.switch(GENERAL_BOT_ID)
    assert app.pending_confirmation == ("RAG add doc.txt", "CONFIRM")


def test_built_in_bot_capability_fields():
    manager = _manager()
    assert manager.bots["calculator"].status == "available"
    assert manager.bots["calculator"].unique_tool == "pension_withdrawal_tax"
    assert manager.bots["drafting"].status == "available"
    assert manager.bots["drafting"].unique_tool == "draft_client_email"
    assert manager.bots["document"].status == "available"
    assert manager.bots["document"].unique_tool == "document_to_pdf"
    assert manager.bots["coding"].status == "experimental"
    assert manager.bots["coding"].unique_tool == "local_development"


def test_no_duplicate_provider_created():
    # create_provider lives on almond_ai.core.application now -- AlmondCore
    # is the single construction point for both the terminal and the
    # desktop app, so patching it here (rather than almond_ai.app) is what
    # actually proves only one provider is ever built.
    import almond_ai.core.application as core_module

    calls = []
    original = core_module.create_provider

    def counting_create_provider(settings):
        calls.append(settings)
        return original(settings)

    core_module.create_provider = counting_create_provider
    try:
        app = AlmondDeveloperApp(_fake_config())
        app.sessions.switch("calculator")
        app.sessions.switch("drafting")
        app.sessions.switch("document")
        app.sessions.switch("coding")
    finally:
        core_module.create_provider = original
    assert len(calls) == 1


def test_new_bot_created_via_ui_flow_persists_and_switches(tmp_path, monkeypatch):
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            new_bot = BotDefinition(
                id="portfolio-analyst",
                name="Portfolio Analyst",
                description="Analyses portfolios",
                instructions="Be precise.",
            )
            app._on_new_bot_created(new_bot)
            await pilot.pause()
            assert "portfolio-analyst" in app.sessions.bots
            assert app.sessions.active_id == "portfolio-analyst"
            saved = load_user_bots(app.bots_path)
            assert any(bot.id == "portfolio-analyst" for bot in saved)
            assert app.query_one("#bot-portfolio-analyst")

    asyncio.run(exercise())
