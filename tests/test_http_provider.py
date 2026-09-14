"""Tests for HttpProvider. No real network call is ever made: the transport
is always replaced with a mock.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from app.errors import ProviderError
from app.providers.base import ProviderMessage
from app.providers.http_provider import HttpProvider


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_http_provider_requires_base_url():
    with pytest.raises(ProviderError):
        HttpProvider("", "secret")


def test_http_provider_success():
    def fake_transport(request):
        assert request.full_url == "https://example.internal/v1/complete"
        assert request.get_header("Authorization") == "Bearer secret"
        return _FakeResponse(json.dumps({"text": "hello"}).encode("utf-8"))

    provider = HttpProvider("https://example.internal", "secret", transport=fake_transport)

    response = provider.complete([ProviderMessage(role="user", content="hi")])

    assert response.text == "hello"
    assert response.provider_name == "approved"


def test_http_provider_no_api_key_omits_auth_header():
    def fake_transport(request):
        assert request.get_header("Authorization") is None
        return _FakeResponse(json.dumps({"text": "hello"}).encode("utf-8"))

    provider = HttpProvider("https://example.internal", transport=fake_transport)

    response = provider.complete([ProviderMessage(role="user", content="hi")])

    assert response.text == "hello"


def test_http_provider_network_error():
    def failing_transport(request):
        raise urllib.error.URLError("boom")

    provider = HttpProvider("https://example.internal", "secret", transport=failing_transport)

    with pytest.raises(ProviderError):
        provider.complete([ProviderMessage(role="user", content="hi")])


def test_http_provider_invalid_json():
    def fake_transport(request):
        return _FakeResponse(b"not json")

    provider = HttpProvider("https://example.internal", "secret", transport=fake_transport)

    with pytest.raises(ProviderError):
        provider.complete([ProviderMessage(role="user", content="hi")])


def test_http_provider_missing_text_field():
    def fake_transport(request):
        return _FakeResponse(json.dumps({"other": 1}).encode("utf-8"))

    provider = HttpProvider("https://example.internal", "secret", transport=fake_transport)

    with pytest.raises(ProviderError):
        provider.complete([ProviderMessage(role="user", content="hi")])
