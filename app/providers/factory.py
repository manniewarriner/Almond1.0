"""Provider selection by config. Adding a provider means adding a branch here,
never changing call sites -- callers only ever depend on the Provider protocol.
"""

from __future__ import annotations

from app.config import AppConfig
from app.errors import ProviderError
from app.local_model import LocalModelServer
from app.providers.base import Provider
from app.providers.fake import FakeProvider
from app.providers.http_provider import HttpProvider
from app.providers.llama_cpp import LlamaCppProvider


def get_local_provider(config: AppConfig) -> LlamaCppProvider:
    """Build Almond's bundled, loopback-only llama.cpp provider.

    Requires no internet, no API key, and no provider_base_url -- it only
    ever talks to the local server it manages on 127.0.0.1.
    """
    server = LocalModelServer(config.local_chat_model)
    return LlamaCppProvider(server)


def get_provider(config: AppConfig) -> Provider:
    if config.provider_name == "fake":
        return FakeProvider()

    if config.provider_name == "local":
        return get_local_provider(config)

    if config.provider_name == "approved":
        if not config.provider_base_url:
            raise ProviderError("provider_name='approved' requires provider_base_url")
        if not config.provider_api_key:
            raise ProviderError("provider_name='approved' requires provider_api_key")
        return HttpProvider(config.provider_base_url, config.provider_api_key)

    raise ProviderError(f"provider {config.provider_name!r} is not available in this build")
