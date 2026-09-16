"""Tests for the shared backend (almond_ai.core.AlmondCore).

Covers what both the terminal and the desktop app rely on: a single
provider instance, independent bot sessions, safe chat streaming with
rollback on error, and the existing PDF backend -- without requiring real
Qwen inference (DeveloperConfig() defaults to the "fake" provider unless
overridden).
"""

from __future__ import annotations

import asyncio

import pytest

from almond_ai.config import DeveloperConfig, ModelSettings
from almond_ai.core import AlmondCore, ModelProviderError
from app.errors import DocumentError, PdfGenerationError


def _fake_config() -> DeveloperConfig:
    return DeveloperConfig(model=ModelSettings(provider="fake"))


def test_core_constructs_one_provider_and_staff_bots():
    core = AlmondCore(_fake_config())
    staff_ids = [bot.id for bot in core.staff_bots()]
    assert staff_ids == ["calculator", "drafting", "document"]
    assert "coding" not in staff_ids
    assert "general" not in staff_ids


def test_staff_bots_reflect_the_same_registry_the_terminal_uses():
    core = AlmondCore(_fake_config())
    # staff_bots() must come from core.sessions.bots (the single shared
    # registry), not a separate desktop-only copy of bot definitions.
    for bot in core.staff_bots():
        assert core.sessions.bots[bot.id] is bot


def test_append_user_message_and_stream_reply_roundtrip():
    core = AlmondCore(_fake_config())

    async def exercise():
        core.append_user_message("general", "Hello Almond")
        chunks = [chunk async for chunk in core.stream_reply("general")]
        return chunks

    chunks = asyncio.run(exercise())
    assert "".join(chunks).strip()
    session = core.sessions.get("general")
    assert session.messages[0] == {"role": "user", "content": "Hello Almond"}
    assert session.messages[1]["role"] == "assistant"


def test_stream_reply_rolls_back_session_on_provider_error():
    core = AlmondCore(_fake_config())

    async def failing_stream(_messages):
        raise ModelProviderError("boom")
        yield ""  # pragma: no cover - never reached, makes this an async generator

    core.provider.stream = failing_stream

    async def exercise():
        core.append_user_message("drafting", "Draft something")
        with pytest.raises(ModelProviderError):
            async for _ in core.stream_reply("drafting"):
                pass

    asyncio.run(exercise())
    assert core.sessions.get("drafting").messages == []


def test_each_bot_has_an_independent_session():
    core = AlmondCore(_fake_config())

    async def exercise():
        core.append_user_message("calculator", "hi calculator")
        async for _ in core.stream_reply("calculator"):
            pass
        core.append_user_message("document", "hi document")
        async for _ in core.stream_reply("document"):
            pass

    asyncio.run(exercise())
    assert core.sessions.get("calculator").messages[0]["content"] == "hi calculator"
    assert core.sessions.get("document").messages[0]["content"] == "hi document"
    assert core.sessions.get("drafting").messages == []


def test_create_pdf_uses_the_existing_branded_pdf_backend(tmp_path):
    core = AlmondCore(_fake_config())
    core.base_config.outputs_dir = tmp_path / "outputs"
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.\n\nSecond paragraph.", encoding="utf-8")

    result = core.create_pdf(str(source))

    assert (tmp_path / "outputs" / "notes-almond.pdf").is_file()
    assert result.pages >= 1
    assert core.tools.get("document_to_pdf").last_status == "success"


def test_create_pdf_without_permission_is_denied(tmp_path):
    core = AlmondCore(_fake_config())
    core.base_config.outputs_dir = tmp_path / "outputs"
    core.permissions.discard("documents:read")
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.", encoding="utf-8")

    with pytest.raises(PermissionError):
        core.create_pdf(str(source))
    assert not (tmp_path / "outputs").exists()


def test_create_pdf_unsupported_type_raises_document_error(tmp_path):
    core = AlmondCore(_fake_config())
    core.base_config.outputs_dir = tmp_path / "outputs"
    source = tmp_path / "sheet.xlsx"
    source.write_bytes(b"not real")

    with pytest.raises((DocumentError, PdfGenerationError)):
        core.create_pdf(str(source))


def test_pdf_excerpt_scope_is_in_audit(tmp_path, monkeypatch):
    from reportlab.pdfgen import canvas as rl_canvas

    events = []
    monkeypatch.setattr(
        "almond_ai.core.application.log_event", lambda path, event: events.append(event)
    )
    core = AlmondCore(_fake_config())
    core.base_config.outputs_dir = tmp_path / "outputs"
    source = tmp_path / "synthetic.pdf"
    canvas = rl_canvas.Canvas(str(source))
    for number in range(3):
        canvas.drawString(72, 700, f"Page {number + 1}")
        canvas.showPage()
    canvas.save()
    core.create_pdf(str(source), fast=True, page_range=(2, 50))
    assert "Included source pages 2–3 of 3." in events[-1].request_summary
    assert "format=streaming" in events[-1].request_summary
