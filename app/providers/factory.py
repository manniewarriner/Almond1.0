"""Provider selection by config. Adding a provider means adding a branch here,
never changing call sites -- callers only ever depend on the Provider protocol.
"""

from __future__ import annotations

from app.config import AppConfig
from app.errors import ProviderError
from app.providers.base import Provider
from app.providers.fake import FakeProvider
from app.providers.http_provider import HttpProvider


def get_provider(config: AppConfig) -> Provider:
    if config.provider_name == "fake":
        return FakeProvider()

    if config.provider_name in {"approved", "local"}:
        if not config.provider_base_url:
            raise ProviderError(
                f"provider_name={config.provider_name!r} requires provider_base_url"
            )
        if config.provider_name == "approved" and not config.provider_api_key:
            raise ProviderError("provider_name='approved' requires provider_api_key")
        return HttpProvider(config.provider_base_url, config.provider_api_key)

    raise ProviderError(f"provider {config.provider_name!r} is not available in this build")
