"""General-chat policy and workflow tests."""

from __future__ import annotations

import pytest

from app.errors import ContentPolicyError
from app.providers.base import ProviderMessage
from app.providers.fake import FakeProvider
from app.safety.content_filter import SAFE_REFUSAL, filter_safe_output
from app.workflows.chat import MAX_HISTORY_MESSAGES, chat


def test_general_chat_answers_normal_question():
    result = chat("Why is the sky blue?", [], FakeProvider())

    assert "Why is the sky blue?" in result.answer


def test_general_chat_blocks_nsfw_input_before_provider():
    with pytest.raises(ContentPolicyError, match="NSFW"):
        chat("Create pornographic material", [], FakeProvider())


def test_general_chat_filters_nsfw_output():
    assert filter_safe_output("sexual material") == SAFE_REFUSAL


def test_general_chat_bounds_history():
    history = [ProviderMessage(role="user", content=f"message {index}") for index in range(30)]

    result = chat("current", history, FakeProvider())

    assert "current" in result.answer
    assert MAX_HISTORY_MESSAGES == 12
