import asyncio

import pytest

from almond_ai.agents.registry import AgentRegistry
from almond_ai.config import DeveloperConfig, ModelSettings, load_developer_config
from almond_ai.models.provider import LocalHTTPProvider, ModelProviderError
from almond_ai.tools.registry import ToolRegistry


def test_agent_switching():
    registry = AgentRegistry()
    assert registry.use("compliance").name == "compliance"
    assert registry.status().name == "compliance"


def test_agent_prompt_enforces_role_and_safety_boundaries():
    registry = AgentRegistry()
    registry.use("email")
    prompt = registry.system_prompt()
    assert "Active role: email" in prompt
    assert "Never claim to" in prompt
    assert "send" in prompt


def test_config_hides_api_key():
    config = DeveloperConfig(model=ModelSettings(api_key="never-display-this"))
    assert "never-display-this" not in str(config.safe_summary())


def test_configuration_loads_nested_environment(monkeypatch):
    monkeypatch.setenv("ALMOND_DEV_MODEL__PROVIDER", "ollama")
    monkeypatch.setenv("ALMOND_DEV_MODEL__MODEL", "synthetic-test-model")
    config = load_developer_config()
    assert config.model.provider == "ollama"
    assert config.model.model == "synthetic-test-model"


def test_default_developer_provider_uses_bundled_local_model():
    config = DeveloperConfig()
    assert config.model.provider == "llama_cpp"
    assert config.model.model == "MiniCPM5-2B-Q4_K_M.gguf"
    assert str(config.model.base_url).startswith("http://127.0.0.1:11435")


def test_permission_checks_fail_closed():
    tools = ToolRegistry()
    with pytest.raises(PermissionError, match="Missing permission"):
        tools.authorize_run("document_search", set())


def test_destructive_tool_requires_confirmation():
    tools = ToolRegistry()
    with pytest.raises(PermissionError, match="confirmation"):
        tools.authorize_run("rag_reindex", {"documents:write"})


def test_llama_cpp_local_provider_disables_thinking_mode(monkeypatch):
    import json

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
            ).encode()

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("almond_ai.models.provider.urllib.request.urlopen", fake_urlopen)

    provider = LocalHTTPProvider(ModelSettings(provider="llama_cpp"))

    async def consume():
        return [chunk async for chunk in provider.stream([{"role": "user", "content": "hi"}])]

    asyncio.run(consume())

    assert captured["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["timeout"] == 120


def test_ollama_provider_does_not_set_llama_cpp_only_fields(monkeypatch):
    import json

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self):
            return json.dumps({"message": {"content": "ok"}}).encode()

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("almond_ai.models.provider.urllib.request.urlopen", fake_urlopen)

    provider = LocalHTTPProvider(ModelSettings(provider="ollama"))

    async def consume():
        return [chunk async for chunk in provider.stream([{"role": "user", "content": "hi"}])]

    asyncio.run(consume())

    assert "chat_template_kwargs" not in captured["payload"]
    assert captured["timeout"] == 45


def test_model_provider_failure_is_wrapped(monkeypatch):
    provider = LocalHTTPProvider(ModelSettings(provider="ollama"))
    monkeypatch.setattr(
        provider, "_complete", lambda messages: (_ for _ in ()).throw(ModelProviderError("failed"))
    )

    async def consume():
        return [chunk async for chunk in provider.stream([{"role": "user", "content": "hi"}])]

    with pytest.raises(ModelProviderError):
        asyncio.run(consume())
