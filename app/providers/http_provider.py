"""HTTP-based real model provider adapter for an approved private endpoint.

No default endpoint is baked in: base_url must come from configuration,
and api_key is optional (some local/internal endpoints need no auth).
This module never makes a network call at import time or during test
collection -- complete() is the only place a request happens, and every
test in this repo replaces the transport with a mock, so no real network
call is ever made here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

from app.errors import ProviderError
from app.providers.base import ProviderMessage, ProviderResponse

DEFAULT_TIMEOUT_SECONDS = 30


class HttpProvider:
    """Adapter for an approved private HTTPS model endpoint.

    Expects POST {"messages": [...]} -> JSON {"text": "..."}. Adjust the
    request/response shape here if the approved endpoint differs; call
    sites never need to change.
    """

    name = "approved"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        transport: Callable[[urllib.request.Request], object] | None = None,
    ) -> None:
        if not base_url:
            raise ProviderError("HttpProvider requires a non-empty base_url")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._default_transport

    def _default_transport(self, request: urllib.request.Request):
        return urllib.request.urlopen(request, timeout=self._timeout_seconds)

    def complete(self, messages: list[ProviderMessage]) -> ProviderResponse:
        payload = json.dumps({"messages": [m.model_dump() for m in messages]}).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = urllib.request.Request(
            url=f"{self._base_url}/v1/complete",
            data=payload,
            method="POST",
            headers=headers,
        )

        try:
            with self._transport(request) as response:
                raw = response.read()
        except urllib.error.URLError as exc:
            raise ProviderError(f"Request to approved provider failed: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Approved provider returned invalid JSON: {exc}") from exc

        text = data.get("text")
        if not isinstance(text, str) or not text:
            raise ProviderError("Approved provider response missing non-empty 'text' field")

        return ProviderResponse(text=text, provider_name=self.name)
