"""ApplicationDispatcher: the shared logic behind the visible TUI and ctl.

These tests exercise the dispatcher directly against a real
AlmondDeveloperApp (via Textual's run_test/Pilot), the same way
tests/test_developer_tui.py exercises the app itself. They use the
"fake" provider so chat never makes a network call.
"""

import asyncio

from almond_ai.app import LIVE_SESSION, AlmondDeveloperApp
from almond_ai.config import DeveloperConfig, ModelSettings
from almond_ai.control.dispatcher import ApplicationDispatcher
from tests.conftest import wait_until_ready


def _fake_config(**kwargs) -> DeveloperConfig:
    return DeveloperConfig(model=ModelSettings(provider="fake"), **kwargs)


def test_status_reports_only_approved_structured_fields():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await wait_until_ready(app, pilot)  # let LoadingScreen finish dismissing
            dispatcher = ApplicationDispatcher(app)
            status = dispatcher.get_status()
            assert status["application_running"] is True
            assert status["ready"] is True
            assert status["startup_state"] == "ready"
            assert status["provider"] == "fake"
            assert status["provider_health"] == "mock"
            assert status["current_agent"] == "general"
            assert status["pdf_tool_available"] is True
            assert status["control_protocol_version"] == 1
            assert not any(hasattr(value, "__dict__") for value in status.values())

    asyncio.run(exercise())


def test_state_includes_status_plus_registries():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            state = dispatcher.get_state()
            assert state["provider"] == "fake"
            assert "general" in state["agents"]
            assert any(tool["name"] == "calculator" for tool in state["tools"])
            assert state["live_confirmation_pending"] is False

    asyncio.run(exercise())


def test_snapshot_reflects_widget_state_not_a_screen_capture():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            snapshot = dispatcher.get_snapshot()
            assert snapshot["view"] == "Chat"
            assert any("General Chat" in line for line in snapshot["header"])
            assert snapshot["input"] == ""
            assert isinstance(snapshot["console"], list)
            assert isinstance(snapshot["status"], dict)

    asyncio.run(exercise())


def test_get_logs_applies_limit_and_severity_filter():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.logs.add("model", "INFO", "one")
            app.logs.add("model", "ERROR", "two")
            dispatcher = ApplicationDispatcher(app)
            entries = dispatcher.get_logs(limit=10, severity="ERROR")
            assert [entry["message"] for entry in entries] == ["two"]
            assert dispatcher.get_logs(limit=0) == []

    asyncio.run(exercise())


def test_automation_chat_never_touches_the_live_session():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            before_transcript = list(app.console_transcript)
            before_messages = list(app.messages)
            result = await dispatcher.chat("automation", "hello")
            assert "DEV MOCK" in result["text"]
            assert app.console_transcript == before_transcript
            assert app.messages == before_messages

    asyncio.run(exercise())


def test_live_chat_appears_in_the_visible_console_exactly_as_typed():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            result = await dispatcher.chat(LIVE_SESSION, "hello there")
            assert "DEV MOCK" in result["text"]
            assert app.messages[-1]["role"] == "assistant"
            assert any("hello there" in entry for entry in app.console_transcript)

    asyncio.run(exercise())


def test_automation_write_command_requires_confirmation_and_is_session_isolated():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            requested = await dispatcher.command("automation", "/rag reindex")
            assert requested["status"] == "confirmation_required"
            assert requested["required_text"] == "CONFIRM"
            # the bridge never touches the live session's confirmation slot
            assert app.pending_confirmation is None

            rejected = await dispatcher.command("automation", "not the confirmation")
            assert rejected["text"] == "Confirmation rejected. Operation cancelled."

    asyncio.run(exercise())


def test_confirmation_is_never_auto_supplied_and_permission_still_applies():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            await dispatcher.command("automation", "/rag reindex")
            # default local user only has documents:read -- confirming must
            # still fail closed on the missing documents:write permission.
            try:
                await dispatcher.command("automation", "CONFIRM")
            except PermissionError as exc:
                assert "documents:write" in str(exc)
            else:
                raise AssertionError("expected a PermissionError")

    asyncio.run(exercise())


def test_confirming_with_permission_performs_the_write_and_reports_it():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        app.permissions.add("documents:write")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            await dispatcher.command("automation", "/rag reindex")
            confirmed = await dispatcher.command("automation", "CONFIRM")
            assert confirmed["status"] == "ok"
            assert "Index refreshed" in confirmed["text"]

    asyncio.run(exercise())


def test_live_command_confirmation_uses_the_shared_pending_confirmation_attribute():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            result = await dispatcher.command(LIVE_SESSION, "/rag reindex")
            assert result["status"] == "confirmation_required"
            assert app.pending_confirmation == ("RAG reindex", "CONFIRM")

    asyncio.run(exercise())


def test_automation_help_returns_text_without_opening_the_help_screen():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            result = await dispatcher.command("automation", "/help")
            assert result["status"] == "ok"
            assert "/rag reindex" in result["text"]
            from almond_ai.app import HelpScreen

            assert not isinstance(app.screen, HelpScreen)

    asyncio.run(exercise())


def test_status_and_config_command_never_leak_the_api_key():
    async def exercise():
        config = DeveloperConfig(
            model=ModelSettings(provider="fake", api_key="super-secret-value"),
        )
        app = AlmondDeveloperApp(config)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            assert "super-secret-value" not in repr(dispatcher.get_status())
            assert "super-secret-value" not in repr(dispatcher.get_state())
            config_text = app._command_output("config", (), session="automation")
            assert "super-secret-value" not in config_text

    asyncio.run(exercise())


def test_logs_redact_known_secret_markers():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.logs.add("model", "ERROR", "api_key=abc123 Authorization: Bearer xyz")
            dispatcher = ApplicationDispatcher(app)
            entries = dispatcher.get_logs(limit=5)
            assert "api_key" not in entries[-1]["message"]
            assert "Authorization" not in entries[-1]["message"]

    asyncio.run(exercise())


def test_automation_exit_is_refused():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            dispatcher = ApplicationDispatcher(app)
            try:
                await dispatcher.command("automation", "/exit")
            except ValueError as exc:
                assert "live" in str(exc)
            else:
                raise AssertionError("expected /exit to be refused for an automation session")
            assert app.is_running

    asyncio.run(exercise())
