"""Async providers for local and OpenAI-compatible runtimes."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import HttpUrl

from almond_ai.config import ModelSettings
from app.errors import ProviderError
from app.local_model import LOCAL_DOC_MODEL_PORT, LocalModelServer

# Sentinel placed on the worker-thread queue to mark the end of a stream.
_STREAM_DONE = object()


class ModelProviderError(RuntimeError):
    pass


class ModelProvider(Protocol):
    name: str

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


class FakeProvider:
    name = "fake"

    def complete_document(self, messages: list[dict[str, str]]) -> str:
        return '{"headings": [], "bullet_lists": [], "numbered_lists": []}'

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        text = "DEV MOCK — local provider not configured. Your prompt was received safely."
        for word in text.split():
            await asyncio.sleep(0)
            yield word + " "


class LocalHTTPProvider:
    def __init__(
        self,
        settings: ModelSettings,
        local_server: LocalModelServer | None = None,
        *,
        document_provider: "LocalHTTPProvider | None" = None,
    ) -> None:
        self.settings = settings
        self.name = settings.provider
        self.local_server = local_server
        # When set (see create_provider()), complete_document() runs
        # against this separate provider/server instead of self -- lets
        # Document-bot AI formatting use a different, more schema-reliable
        # local model than chat/drafting without touching either call path.
        self.document_provider = document_provider

    def _payload(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool,
        drafting: bool = False,
        document: bool = False,
    ) -> tuple[str, dict]:
        base = str(self.settings.base_url).rstrip("/")
        if self.settings.provider == "ollama":
            url = f"{base}/api/chat"
            payload = {"model": self.settings.model, "messages": messages, "stream": stream}
        else:
            url = f"{base}/v1/chat/completions"
            payload = {
                "model": self.settings.model,
                "messages": messages,
                "stream": stream,
                "temperature": self.settings.temperature,
            }
            if self.settings.provider == "llama_cpp":
                # Supported by the bundled MiniCPM5 template (and earlier Qwen template).
                payload["chat_template_kwargs"] = {"enable_thinking": False}
        if drafting or document:
            from almond_ai.core.drafting import DRAFT_MAX_TOKENS

            if self.settings.provider == "ollama":
                payload["think"] = False
                payload["options"] = {
                    "temperature": 0,
                    "seed": 42,
                    "num_predict": DRAFT_MAX_TOKENS,
                }
            else:
                payload.update(temperature=0, seed=42, max_tokens=DRAFT_MAX_TOKENS)
                if self.settings.provider == "llama_cpp":
                    payload["cache_prompt"] = True
        if document:
            if self.settings.provider == "ollama":
                payload["format"] = "json"
            else:
                payload["response_format"] = {"type": "json_object"}
        return url, payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    def _timeout_seconds(self) -> int:
        return 120 if self.settings.provider == "llama_cpp" else 45

    def complete_document(self, messages: list[dict[str, str]]) -> str:
        target = self.document_provider or self
        if target.settings.base_url.host not in {"127.0.0.1", "localhost", "[::1]", "::1"}:
            raise ModelProviderError("AI document formatting requires a local model endpoint")
        try:
            return target._complete(messages, document=True)
        except ProviderError as exc:
            if target is self.document_provider:
                # The dedicated document model's server failed to start (e.g. a
                # corrupted/missing gguf on disk -- this happened for real with
                # Qwen3.5-2B-Q4_K_M.gguf). Rather than hard-failing the whole
                # Document bot, fall back to the main chat model's server, which
                # is already known-healthy. Once the document model file is
                # repaired, target._complete() above will succeed again and this
                # fallback simply won't trigger -- don't "simplify" it away.
                try:
                    return self._complete(messages, document=True)
                except ProviderError:
                    pass
            raise ModelProviderError("The local document model could not start") from exc

    def _complete(self, messages: list[dict[str, str]], *, document: bool = False) -> str:
        if self.local_server is not None:
            self.local_server.start()
        url, payload = self._payload(messages, stream=False, document=document)
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds()) as response:
                data = json.loads(response.read())
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ModelProviderError(f"Model connection failed: {self.name}") from exc
        try:
            if document:
                finish = (
                    data.get("done_reason")
                    if self.settings.provider == "ollama"
                    else data["choices"][0].get("finish_reason")
                )
                if finish == "length":
                    raise ModelProviderError("Document formatting reached the output limit")
            return (
                data["message"]["content"]
                if self.settings.provider == "ollama"
                else data["choices"][0]["message"]["content"]
            )
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ModelProviderError("Model returned an invalid response") from exc

    def _stream_worker(
        self, messages: list[dict[str, str]], out: queue.Queue, drafting: bool = False
    ) -> None:
        """Runs on a background thread: pushes text deltas onto `out` as the
        server emits them, so the async side never blocks the event loop on
        a socket read. Ends with exactly one `_STREAM_DONE` (success) or one
        `ModelProviderError` instance (failure) as the final item.
        """
        try:
            if self.local_server is not None:
                self.local_server.start()
            url, payload = self._payload(messages, stream=True, drafting=drafting)
            request = urllib.request.Request(
                url, data=json.dumps(payload).encode(), headers=self._headers(), method="POST"
            )
            with urllib.request.urlopen(request, timeout=self._timeout_seconds()) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if drafting:
                        body = line.removeprefix("data:").strip()
                        try:
                            data = json.loads(body)
                        except json.JSONDecodeError:
                            data = {}
                        if not isinstance(data, dict):
                            continue
                        choices = data.get("choices")
                        choice = choices[0] if isinstance(choices, list) and choices else {}
                        finish_reason = (
                            choice.get("finish_reason") if isinstance(choice, dict) else None
                        )
                        if data.get("done_reason") == "length" or finish_reason == "length":
                            out.put(
                                ModelProviderError(
                                    "Draft reached the output limit. Request a shorter draft "
                                    "or format a smaller text section."
                                )
                            )
                            return
                    if self.settings.provider == "ollama":
                        chunk = self._ollama_delta(line)
                    else:
                        chunk = self._sse_delta(line)
                        if chunk is None and line.removeprefix("data: ").strip() == "[DONE]":
                            break
                    if chunk:
                        out.put(chunk)
        except (
            OSError,
            urllib.error.URLError,
            ProviderError,
            ValueError,
            TypeError,
            AttributeError,
        ) as exc:
            err = ModelProviderError(f"Model connection failed: {self.name}")
            err.__cause__ = exc
            out.put(err)
            return
        out.put(_STREAM_DONE)

    @staticmethod
    def _sse_delta(line: str) -> str | None:
        if not line.startswith("data:"):
            return None
        body = line[len("data:") :].strip()
        if body == "[DONE]":
            return None
        try:
            data = json.loads(body)
            return data["choices"][0]["delta"].get("content") or None
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return None

    @staticmethod
    def _ollama_delta(line: str) -> str | None:
        try:
            data = json.loads(line)
            return data.get("message", {}).get("content") or None
        except json.JSONDecodeError:
            return None

    async def stream_draft(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for chunk in self.stream(messages, drafting=True):
            yield chunk

    async def stream(
        self, messages: list[dict[str, str]], *, drafting: bool = False
    ) -> AsyncIterator[str]:
        out: queue.Queue = queue.Queue()
        thread = threading.Thread(
            target=self._stream_worker, args=(messages, out, drafting), daemon=True
        )
        thread.start()
        while True:
            item = await asyncio.to_thread(out.get)
            if item is _STREAM_DONE:
                return
            if isinstance(item, ModelProviderError):
                raise item
            yield item

    def is_ready(self) -> bool:
        return self.local_server is not None and self.local_server.is_ready()

    def stop(self) -> None:
        if self.local_server is not None:
            self.local_server.stop()
        if self.document_provider is not None:
            self.document_provider.stop()


def create_provider(settings: ModelSettings) -> ModelProvider:
    if settings.provider == "fake":
        return FakeProvider()
    if settings.provider != "llama_cpp":
        return LocalHTTPProvider(settings)
    server = LocalModelServer(settings.model)
    document_provider = None
    if settings.document_model and settings.document_model != settings.model:
        doc_server = LocalModelServer(settings.document_model, port=LOCAL_DOC_MODEL_PORT)
        doc_settings = settings.model_copy(
            update={
                "model": settings.document_model,
                "base_url": HttpUrl(f"http://127.0.0.1:{LOCAL_DOC_MODEL_PORT}"),
            }
        )
        document_provider = LocalHTTPProvider(doc_settings, doc_server)
    return LocalHTTPProvider(settings, server, document_provider=document_provider)
