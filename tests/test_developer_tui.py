import asyncio

from textual.widgets import TextArea

from almond_ai.app import AlmondDeveloperApp, HelpScreen
from almond_ai.config import DeveloperConfig
from tests.conftest import wait_until_ready


def test_tui_starts_and_renders_dashboard():
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.query_one("#console")
            assert app.query_one("#system-status")
            assert app.query_one("#welcome-panel")
            assert app.query_one("#navigation")
            assert app.query_one("#bot-calculator")
            assert app.query_one("#bot-general")

    asyncio.run(exercise())


def test_each_navigation_destination_has_a_dedicated_view():
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for name, view_id in app.VIEW_IDS.items():
                app.show_view(name)
                await pilot.pause()
                assert app.active_view == name
                assert app.query_one(f"#{view_id}").has_class("view-active")

    asyncio.run(exercise())


def test_help_uses_overlay_without_writing_console():
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            console = app.query_one("#console")
            initial_lines = len(console.lines)
            app.run_command("help", ())
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            assert len(console.lines) == initial_lines

    asyncio.run(exercise())


def test_config_opens_structured_settings_view():
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.run_command("config", ())
            await pilot.pause()
            assert app.active_view == "Settings"
            assert app.query_one("#view-settings").has_class("view-active")

    asyncio.run(exercise())


def test_sidebar_and_composer_stay_usable_at_both_supported_sizes():
    async def exercise():
        for size in ((120, 40), (100, 35)):
            app = AlmondDeveloperApp(DeveloperConfig())
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                sidebar = app.query_one("#navigation")
                composer = app.query_one("#composer", TextArea)
                assert sidebar.styles.display != "none"
                assert composer.region.width > 0
                assert app.query_one("#bot-drafting").region.width > 0

    asyncio.run(exercise())


def test_calculator_command_uses_deterministic_backend():
    app = AlmondDeveloperApp(DeveloperConfig())
    assert app._calculate(("percentage-return", "100", "110")) == (
        "percentage-return: [#F15A24]10%[/]"
    )
    assert app._calculate(("absolute-change", "100", "90")) == ("absolute-change: [#F15A24]-10[/]")


def test_specialized_commands_route_into_model_worker(monkeypatch):
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        captured = []
        monkeypatch.setattr(app, "run_chat", captured.append)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.run_command("summarise", ("quarterly", "update"))
            app.run_command("draft", ("client", "note"))
            app.run_command("analyse", ("risk", "scenario"))
            assert len(captured) == 3
            assert captured[0].startswith("Summarise clearly")
            assert captured[1].startswith("Draft polished")
            assert captured[2].startswith("Analyse carefully")

    asyncio.run(exercise())


def test_tool_calculator_executes_after_permission_check():
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        app.permissions.add("calculator:use")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            output = app._command_output(
                "tool", ("run", "calculator", "absolute-change", "12", "20")
            )
            assert output == "absolute-change: [#F15A24]8[/]"
            assert app.tools.get("calculator").last_status == "success"

    asyncio.run(exercise())


def test_approval_tool_defers_execution():
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            output = app._command_output("tool", ("run", "rag_reindex"))
            assert "requires approval" in output
            assert app.pending_confirmation == ("TOOL rag_reindex", "CONFIRM")

    asyncio.run(exercise())


def test_enter_submits_and_ctrl_j_inserts_newline():
    # Modifier+Enter combinations (Ctrl+Enter, Shift+Enter, ...) are not
    # reliably reported as distinct key events by real terminals -- they
    # arrive identical to plain Enter. The composer must therefore submit
    # on plain Enter and use Ctrl+J (a real, distinct byte) for newlines.
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await wait_until_ready(app, pilot)  # let LoadingScreen dismiss so focus lands
            composer = app.query_one("#composer", TextArea)
            composer.focus()
            await pilot.pause()

            await pilot.press(*"AAA")
            await pilot.press("ctrl+j")
            await pilot.press(*"BBB")
            await pilot.pause()
            assert composer.text == "AAA\nBBB"

            await pilot.press("enter")
            await pilot.pause()
            assert composer.text == ""
            assert app.history[-1] == "AAA\nBBB"

    asyncio.run(exercise())


def test_production_requires_exact_confirmation():
    async def exercise():
        app = AlmondDeveloperApp(DeveloperConfig())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.run_command("deploy", ("production",))
            assert app.pending_confirmation == ("production deployment", "DEPLOY")

    asyncio.run(exercise())
