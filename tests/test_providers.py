"""Tests for the provider interface: fake provider and the provider factory."""

from __future__ import annotations

import pytest

from app.config import AppConfig
from app.errors import ProviderError
from app.providers.base import ProviderMessage
from app.providers.factory import get_provider
from app.providers.fake import FakeProvider
from app.providers.http_provider import HttpProvider


def test_fake_provider_echoes_last_user_message():
    provider = FakeProvider()
    messages = [
        ProviderMessage(role="system", content="sys"),
        ProviderMessage(role="user", content="What is KYC?"),
    ]

    response = provider.complete(messages)

    assert response.provider_name == "fake"
    assert "What is KYC?" in response.text


def test_fake_provider_handles_no_user_messages():
    provider = FakeProvider()

    response = provider.complete([ProviderMessage(role="system", content="sys")])

    assert response.text


def test_get_provider_fake():
    provider = get_provider(AppConfig(provider_name="fake"))

    assert isinstance(provider, FakeProvider)


def test_get_provider_local_requires_base_url():
    with pytest.raises(ProviderError):
        get_provider(AppConfig(provider_name="local"))


def test_get_provider_local_with_base_url():
    provider = get_provider(
        AppConfig(provider_name="local", provider_base_url="http://localhost:11434")
    )

    assert isinstance(provider, HttpProvider)


def test_get_provider_approved_requires_api_key():
    with pytest.raises(ProviderError):
        get_provider(
            AppConfig(provider_name="approved", provider_base_url="https://example.internal")
        )


def test_get_provider_approved_with_credentials():
    provider = get_provider(
        AppConfig(
            provider_name="approved",
            provider_base_url="https://example.internal",
            provider_api_key="secret",
        )
    )

    assert isinstance(provider, HttpProvider)
