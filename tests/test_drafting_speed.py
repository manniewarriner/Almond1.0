"""Draft-only request budgets, provider isolation, streaming and fact-preserving cleanup."""

import asyncio
import json

import pytest

from almond_ai.config import DeveloperConfig, ModelSettings
from almond_ai.core import AlmondCore
from almond_ai.core.drafting import (
    DRAFT_INPUT_BYTES,
    DRAFT_MAX_TOKENS,
    DRAFT_SYSTEM_PROMPT,
    drafting_messages,
    normalize_drafting_text,
)
from almond_ai.models.provider import LocalHTTPProvider, ModelProviderError


def test_fresh_draft_excludes_previous_client_but_retains_full_request():
    request = "Draft a client email.\nPurpose: Ask Alex for availability."
    history = [
        {"role": "user", "content": "Another client's private context"},
        {"role": "assistant", "content": "Previous draft"},
        {"role": "user", "content": request},
    ]
    result = drafting_messages(history)
    assert result == [
        {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
        {"role": "user", "content": request},
    ]
    assert len(history) == 3


def test_revision_keeps_previous_draft_and_instruction():
    history = [
        {"role": "user", "content": "Ask Alex about Tuesday at 10am; not confirmed."},
        {"role": "assistant", "content": "Subject: Meeting\nDoes Tuesday at 10am suit you?"},
        {"role": "user", "content": "Make it warmer."},
    ]
    assert drafting_messages(history)[1:] == history


def test_normalization_preserves_figures_lists_and_paragraphs():
    raw = "\ufeffAmount:\xa0 £1,234.56\r\n\r\n-  -12.5%\r\n- co-ownership\n\nA bro\u00ad\nken line."
    assert normalize_drafting_text(raw) == (
        "Amount: £1,234.56\n\n- -12.5%\n- co-ownership\n\nA broken line."
    )


def test_oversized_input_rejected_without_truncation():
    history = [{"role": "user", "content": "£" * DRAFT_INPUT_BYTES}]
    with pytest.raises(ModelProviderError, match="too long"):
        drafting_messages(history)
    assert history[0]["content"] == "£" * DRAFT_INPUT_BYTES


def test_cleanup_preserves_nested_list_indentation():
    assert normalize_drafting_text("Heading\n- Item\n    - Nested  item") == (
        "Heading\n- Item\n    - Nested item"
    )


def test_later_revisions_keep_original_qualifications():
    history = [
        {"role": "user", "content": "Draft a client email.\nPurpose: Tuesday is not confirmed."},
        {"role": "assistant", "content": "Original draft"},
        {"role": "user", "content": "Make it warmer."},
        {"role": "assistant", "content": "Warmer draft"},
        {"role": "user", "content": "Now shorten it."},
    ]
    assert drafting_messages(history)[1:] == history


def test_local_startup_failure_does_not_leave_draft_waiting_forever():
    from app.errors import ProviderError

    class BrokenServer:
        def start(self):
            raise ProviderError("Synthetic startup failure")

    provider = LocalHTTPProvider(ModelSettings(provider="llama_cpp"), BrokenServer())

    async def consume():
        return [chunk async for chunk in provider.stream_draft([])]

    async def exercise():
        with pytest.raises(ModelProviderError):
            await asyncio.wait_for(consume(), timeout=2)

    asyncio.run(exercise())


@pytest.mark.parametrize("provider_name", ["llama_cpp", "ollama", "openai_compatible"])
def test_draft_options_do_not_change_general_chat(provider_name):
    provider = LocalHTTPProvider(ModelSettings(provider=provider_name, temperature=0.7))
    messages = [{"role": "user", "content": "Synthetic request"}]
    before = provider._payload(messages, stream=True)
    _, draft = provider._payload(messages, stream=True, drafting=True)
    assert provider._payload(messages, stream=True) == before
    assert provider.settings.temperature == 0.7
    if provider_name == "ollama":
        assert draft["think"] is False
        assert draft["options"]["num_predict"] == DRAFT_MAX_TOKENS
        assert draft["options"]["temperature"] == 0
    else:
        assert draft["temperature"] == 0
        assert draft["max_tokens"] == DRAFT_MAX_TOKENS
        assert draft["seed"] == 42
    if provider_name == "llama_cpp":
        assert draft["chat_template_kwargs"] == {"enable_thinking": False}
        assert draft["cache_prompt"] is True


def test_core_routes_only_drafting_to_fast_profile():
    core = AlmondCore(DeveloperConfig(model=ModelSettings(provider="fake")))
    captured = []

    class SpyProvider:
        async def stream(self, messages):
            captured.append(("general", messages))
            yield "Reply"

        async def stream_draft(self, messages):
            captured.append(("draft", messages))
            yield "Subject: Draft"

    core.provider = SpyProvider()

    async def exercise():
        for bot in ("general", "drafting"):
            core.append_user_message(bot, "Synthetic request")
            _ = [part async for part in core.stream_reply(bot)]

    asyncio.run(exercise())
    assert [kind for kind, _ in captured] == ["general", "draft"]
    assert captured[0][1][0]["content"] == core.system_prompt_for_bot("general")
    assert captured[1][1][0]["content"] == DRAFT_SYSTEM_PROMPT


def test_budget_failure_rolls_back_pending_request():
    core = AlmondCore(DeveloperConfig(model=ModelSettings(provider="fake")))
    core.append_user_message("drafting", "x" * 10000)

    async def exercise():
        with pytest.raises(ModelProviderError, match="too long"):
            _ = [part async for part in core.stream_reply("drafting")]

    asyncio.run(exercise())
    assert core.sessions.get("drafting").messages == []


def test_streaming_output_limit_is_reported_not_silently_saved(monkeypatch):
    captured = []

    class Response:
        def __enter__(self):
            return iter(
                [
                    b'data: {"choices":[{"delta":{"content":"Subject: Draft"}}]}\n',
                    b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n',
                ]
            )

        def __exit__(self, *args):
            return False

    def request(req, **kwargs):
        captured.append(json.loads(req.data))
        return Response()

    monkeypatch.setattr("almond_ai.models.provider.urllib.request.urlopen", request)
    provider = LocalHTTPProvider(ModelSettings(provider="llama_cpp"))

    async def exercise():
        received = []
        with pytest.raises(ModelProviderError, match="output limit"):
            async for part in provider.stream_draft([{"role": "user", "content": "Draft"}]):
                received.append(part)
        assert received == ["Subject: Draft"]

    asyncio.run(exercise())
    assert captured[0]["max_tokens"] == DRAFT_MAX_TOKENS
