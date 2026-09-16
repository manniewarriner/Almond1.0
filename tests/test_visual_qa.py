"""Visual QA at multiple terminal sizes -- no clipping, no broken layout."""

import asyncio

from textual.widgets import TextArea

from almond_ai.app import AlmondDeveloperApp
from almond_ai.config import DeveloperConfig, ModelSettings


def _fake_config(**kwargs) -> DeveloperConfig:
    return DeveloperConfig(model=ModelSettings(provider="fake"), **kwargs)


def test_layout_survives_120x40_100x35_160x45():
    async def exercise():
        for size in ((120, 40), (100, 35), (160, 45)):
            app = AlmondDeveloperApp(_fake_config())
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                sidebar = app.query_one("#navigation")
                composer = app.query_one("#composer", TextArea)
                console = app.query_one("#console")
                assert sidebar.region.width > 0
                assert composer.region.width > 0
                assert console.region.height > 0
                for bot_id in ("calculator", "drafting", "document", "coding"):
                    item = app.query_one(f"#bot-{bot_id}")
                    assert item.region.width > 0
                    # Unicode icon rendered, not clipped to an empty string.
                    assert item.content.strip()

    asyncio.run(exercise())


def test_long_message_does_not_break_console(monkeypatch):
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()

            async def long_stream(_messages):
                yield "word " * 400

            monkeypatch.setattr(app.provider, "stream", long_stream)
            app.run_chat("give me a very long answer")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.messages[-1]["content"].strip()

    asyncio.run(exercise())


def test_switching_through_every_bot_at_small_size():
    async def exercise():
        app = AlmondDeveloperApp(_fake_config())
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            for bot_id in ("calculator", "drafting", "document", "coding", "general"):
                app.switch_bot(bot_id)
                await pilot.pause()
                assert app.sessions.active_id == bot_id
                assert app.query_one("#welcome-heading").region.width > 0

    asyncio.run(exercise())
