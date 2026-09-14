"""Provider for Almond's bundled, loopback-only llama.cpp server."""

from __future__ import annotations

import http.client
import json
from collections.abc import Callable

from app.errors import ProviderError
from app.local_model import LOCAL_MODEL_PORT, LOOPBACK_HOST, LocalModelServer
from app.providers.base import ProviderMessage, ProviderResponse

DEFAULT_TIMEOUT_SECONDS = 120


class LlamaCppProvider:
    name = "local:llama.cpp"

    def __init__(
        self,
        server: LocalModelServer | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        transport: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.server = server
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._default_transport

    def _default_transport(self, payload: bytes) -> bytes:
        connection = http.client.HTTPConnection(
            LOOPBACK_HOST, LOCAL_MODEL_PORT, timeout=self._timeout_seconds
        )
        try:
            connection.request(
                "POST",
                "/v1/chat/completions",
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            raw = response.read()
        except OSError as exc:
            raise ProviderError("The local model is unavailable.") from exc
        finally:
            connection.close()
        if response.status != 200:
            raise ProviderError(f"The local model returned HTTP {response.status}.")
        return raw

    def complete(self, messages: list[ProviderMessage]) -> ProviderResponse:
        if self.server is not None:
            self.server.start()
        payload = json.dumps(
            {
                "messages": [message.model_dump() for message in messages],
                "temperature": 0.7,
                "max_tokens": 512,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode("utf-8")
        raw = self._transport(payload)
        try:
            data = json.loads(raw)
            text = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("The local model returned an invalid response.") from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("The local model returned no response.")
        return ProviderResponse(text=text.strip(), provider_name=self.name)
