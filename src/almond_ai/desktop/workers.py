"""Off-GUI-thread workers.

Every call into AlmondCore that can block -- model inference/streaming,
PDF generation -- runs on a QThread, never on the Qt GUI thread. Each
worker owns its own short-lived asyncio event loop (`asyncio.run`) where
needed; AlmondCore itself has no event-loop affinity, so this is safe.
"""

from __future__ import annotations

import asyncio
import time

from PySide6.QtCore import QThread, Signal

from almond_ai.core import AlmondCore, ModelProviderError
from app.errors import ContentPolicyError, DocumentError, PdfGenerationError, ProviderError
from app.pdf.service import PdfResult
from app.safety.content_filter import enforce_safe_input


class ChatStreamWorker(QThread):
    """Runs one chat turn for `bot_id` and streams the reply back via signals.

    Uses the exact same `AlmondCore.append_user_message` /
    `AlmondCore.stream_reply` the terminal's `run_chat` uses, and the same
    shared `enforce_safe_input` safety gate -- this file contains no
    reimplementation of the chat/model logic itself, only the thread
    plumbing around it.
    """

    chunk_received = Signal(str)  # cumulative response text so far
    finished_ok = Signal(str, float, float)  # response text, thinking secs, total secs
    blocked = Signal(str)  # rejected by the safety filter, no model call made
    failed = Signal(str)  # model/provider error

    def __init__(self, core: AlmondCore, bot_id: str, prompt: str, parent=None) -> None:
        super().__init__(parent)
        self._core = core
        self._bot_id = bot_id
        self._prompt = prompt

    def run(self) -> None:
        try:
            asyncio.run(self._stream())
        except Exception as exc:  # noqa: BLE001 - never crash silently off-thread
            self.failed.emit(str(exc))

    async def _stream(self) -> None:
        try:
            # MainWindow._send already calls enforce_safe_input before ever
            # constructing this worker -- this second call is deliberate
            # defense-in-depth (the worker must never trust text handed to
            # it, in case a future caller starts one directly), not a gap
            # to close by removing one of the two checks.
            prompt = enforce_safe_input(self._prompt)
        except ContentPolicyError as exc:
            self.blocked.emit(str(exc))
            return
        self._core.append_user_message(self._bot_id, prompt)
        response = ""
        started = time.monotonic()
        first_chunk_at: float | None = None
        try:
            async for chunk in self._core.stream_reply(self._bot_id):
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic()
                response += chunk
                self.chunk_received.emit(response)
        except ModelProviderError as exc:
            self.failed.emit(str(exc))
            return
        finished = time.monotonic()
        thinking_seconds = (first_chunk_at or finished) - started
        total_seconds = finished - started
        self.finished_ok.emit(response, thinking_seconds, total_seconds)


class PdfCreateWorker(QThread):
    """Runs `AlmondCore.create_pdf` (permission check + render + audit) off-thread."""

    finished_ok = Signal(object)  # PdfResult
    failed = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        core: AlmondCore,
        source: str,
        title: str | None,
        *,
        fast: bool = False,
        page_range: tuple[int, int] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._core = core
        self._source = source
        self._title = title
        self._fast = fast
        self._page_range = page_range

    def run(self) -> None:
        try:
            result: PdfResult = self._core.create_pdf(
                self._source,
                self._title,
                fast=self._fast,
                page_range=self._page_range,
                progress=self.progress.emit,
                ai_format=True,
            )
        except PermissionError as exc:
            # ToolRegistry.authorize_run's PermissionError messages are
            # already complete/human-readable ("Missing permission: ...",
            # "Tool disabled", "Explicit confirmation required") -- do not
            # re-prefix them, or "Tool disabled" renders as the nonsensical
            # "Missing permission: Tool disabled".
            self.failed.emit(str(exc))
        except (DocumentError, PdfGenerationError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(result)


class CalculatorScanWorker(QThread):
    """Runs `AlmondCore.scan_document_for_calculator` off-thread."""

    finished_ok = Signal(dict)  # field key -> found value (or None)
    failed = Signal(str)

    def __init__(
        self, core: AlmondCore, source: str, field_keys: tuple[str, ...], parent=None
    ) -> None:
        super().__init__(parent)
        self._core = core
        self._source = source
        self._field_keys = field_keys

    def run(self) -> None:
        try:
            result = self._core.scan_document_for_calculator(self._source, self._field_keys)
        except PermissionError as exc:
            self.failed.emit(str(exc))
        except (DocumentError, ModelProviderError, ProviderError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash silently off-thread
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(result)


class ModelStartupWorker(QThread):
    """Warms up the bundled local model server (if any) without blocking the GUI."""

    ready = Signal()
    failed = Signal(str)

    def __init__(self, core: AlmondCore, parent=None) -> None:
        super().__init__(parent)
        self._core = core

    def run(self) -> None:
        local_server = getattr(self._core.provider, "local_server", None)
        if local_server is None:
            self.ready.emit()
            return
        try:
            local_server.start()
        except Exception as exc:  # noqa: BLE001 - surface, e.g. ProviderError
            self.failed.emit(str(exc))
            return
        self.ready.emit()
