"""Tests for the bundled llama.cpp provider."""

from __future__ import annotations

import json

from app.providers.base import ProviderMessage
from app.providers.llama_cpp import LlamaCppProvider


def test_llama_cpp_provider_uses_openai_compatible_local_request():
    def transport(payload: bytes) -> bytes:
        data = json.loads(payload)
        assert data["messages"][-1] == {"role": "user", "content": "Hello"}
        assert data["stream"] is False
        assert data["chat_template_kwargs"] == {"enable_thinking": False}
        return json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": "Local answer"}}]}
        ).encode()

    provider = LlamaCppProvider(transport=transport)
    result = provider.complete([ProviderMessage(role="user", content="Hello")])

    assert result.text == "Local answer"
    assert result.provider_name == "local:llama.cpp"


def test_llama_cpp_provider_source_is_loopback_only():
    import inspect

    import app.providers.llama_cpp as provider_module

    source = inspect.getsource(provider_module)

    assert "LOOPBACK_HOST" in source
    assert "https://" not in source
    assert "urllib" not in source
