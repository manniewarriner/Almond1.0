"""AlmondCore: the shared backend both UIs drive.

Owns exactly one model provider, one bot/session layer, and the document/
permission/audit services -- constructed once and handed to whichever UI
(Textual terminal or Qt desktop) is launched. Neither UI may construct its
own provider or session manager; both call into this class so there is
never more than one local model loaded and never two divergent copies of
"what a chat turn does."
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path

from almond_ai.agents.registry import AgentRegistry
from almond_ai.bots.models import BotDefinition
from almond_ai.bots.registry import BUILT_IN_BOTS, GENERAL_BOT, STAFF_BOT_IDS, bot_system_prompt
from almond_ai.bots.sessions import SessionManager
from almond_ai.bots.storage import load_user_bots
from almond_ai.config import DeveloperConfig, load_developer_config
from almond_ai.core.calculator_extraction import extract_calculator_fields
from almond_ai.core.document_formatting import format_document
from almond_ai.core.drafting import drafting_messages
from almond_ai.evaluation.runner import EvaluationRunner
from almond_ai.logging.service import LogService
from almond_ai.models.provider import ModelProviderError, create_provider
from almond_ai.rag.service import RAGService
from almond_ai.tools.registry import ToolRegistry
from app.audit.log import AuditEvent, log_event
from app.config import load_config
from app.documents.content_extract import extract_document
from app.errors import DocumentError, PdfGenerationError, ProviderError
from app.pdf import create_branded_pdf
from app.pdf.service import PdfResult
from app.security.permissions import resolve_requester

__all__ = ["AlmondCore", "ModelProviderError"]


def _cause_chain(exc: BaseException, max_len: int = 280) -> str:
    """`str(exc)` for `exc` and every exception chained onto it via `raise
    ... from cause`, joined outermost-first -- the layers between a raw
    provider/subprocess failure and the generic message a caller of
    create_pdf() sees each re-wrap with `from exc`, so the specific reason
    (e.g. a corrupted model file) only survives in this chain, never in
    `str(exc)` alone.
    """
    parts = []
    current: BaseException | None = exc
    while current is not None:
        text = str(current)
        if text:
            parts.append(text)
        current = current.__cause__
    return " <- caused by: ".join(parts)[:max_len]


class AlmondCore:
    """Constructs and owns every backend service Almond needs.

    `config`/`base_config` are exposed as plain attributes (not copies) so
    a caller such as a test can mutate `core.base_config.outputs_dir` or
    `core.permissions` in place and have every method on this instance see
    the change immediately -- both UIs and the test suite rely on that.
    """

    def __init__(self, config: DeveloperConfig | None = None) -> None:
        self.config = config or load_developer_config()
        self.base_config = load_config()
        self.provider = create_provider(self.config.model)
        self.agents = AgentRegistry()
        self.tools = ToolRegistry()
        self.rag = RAGService(
            self.base_config.documents_dir, self.base_config.users_file, self.config.embedding_model
        )
        requester = resolve_requester(self.base_config.users_file, self.config.user_id)
        self.permissions = set(requester.permissions)
        self.evals = EvaluationRunner()
        self.logs = LogService()
        self.bots_path = Path(self.base_config.data_dir) / "bots.json"
        user_bots = load_user_bots(self.bots_path)
        self.sessions = SessionManager([GENERAL_BOT, *BUILT_IN_BOTS, *user_bots])

    # -- bots -----------------------------------------------------------

    def system_prompt_for_bot(self, bot_id: str) -> str:
        return bot_system_prompt(self.sessions.bots[bot_id], self.agents.system_prompt())

    def staff_bots(self) -> list[BotDefinition]:
        """Specialist bots shown in the staff-facing desktop app.

        Excludes Coding (terminal/developer-only) and any user-created bot
        from the "+ New Bot" flow, which the desktop app doesn't expose.
        """
        return [
            self.sessions.bots[bot_id] for bot_id in STAFF_BOT_IDS if bot_id in self.sessions.bots
        ]

    # -- chat -------------------------------------------------------------

    def append_user_message(self, bot_id: str, prompt: str) -> None:
        """Append an already safety-checked prompt to bot_id's session.

        Callers must validate `prompt` with
        `app.safety.content_filter.enforce_safe_input` first -- this method
        does not re-validate, so both UIs go through the exact same
        validation function rather than each having their own copy of it.
        """
        self.sessions.get(bot_id).messages.append({"role": "user", "content": prompt})

    async def stream_reply(self, bot_id: str) -> AsyncIterator[str]:
        """Stream the assistant's reply to the most recently appended user message.

        On `ModelProviderError`, rolls the session back to the state before
        that user message (a failed turn never poisons history) and
        re-raises. On success, appends the full assistant reply to the
        session before returning.
        """
        session = self.sessions.get(bot_id)
        before = len(session.messages) - 1
        provider_messages = [
            {"role": "system", "content": self.system_prompt_for_bot(bot_id)},
            *session.messages[-20:],
        ]
        response = ""
        try:
            stream = self.provider.stream
            if bot_id == "drafting":
                provider_messages = drafting_messages(session.messages)
                stream = getattr(self.provider, "stream_draft", stream)
            async for chunk in stream(provider_messages):
                response += chunk
                yield chunk
        except ModelProviderError:
            del session.messages[before:]
            raise
        session.messages.append({"role": "assistant", "content": response})

    # -- documents / PDF --------------------------------------------------

    def create_pdf(
        self,
        source: str,
        title: str | None = None,
        *,
        fast: bool = False,
        page_range: tuple[int, int] | None = None,
        progress=None,
        ai_format: bool = False,
    ) -> PdfResult:
        """Create a branded PDF from `source` via the existing PDF backend.

        Authorizes against the `document_to_pdf` tool's permission,
        generates and verifies the PDF, and writes an audit event either
        way -- shared by both `/pdf create` in the terminal and the
        Document bot's "Create PDF" action in the desktop app so there is
        exactly one PDF code path and one audit trail for it.
        """
        tool = self.tools.get("document_to_pdf")
        try:
            self.tools.authorize_run(tool.name, self.permissions)
            formatter = None
            if ai_format:
                complete = getattr(self.provider, "complete_document", None)
                if complete is None:
                    raise PdfGenerationError(
                        "The configured model does not support document formatting"
                    )
                formatter = partial(format_document, complete=complete, progress=progress)
            result = create_branded_pdf(
                Path(source),
                self.base_config.outputs_dir,
                title,
                fast=fast,
                page_range=page_range,
                progress=progress,
                formatter=formatter,
            )
            if ai_format and self.config.model.provider == "fake":
                result.formatting_method = "mock_structure"
        except PermissionError as exc:
            self._audit_pdf(
                source,
                outcome="denied",
                error_category="permission_denied",
                streaming=fast,
                formatting_method="ai_structure" if ai_format else "standard",
            )
            self.logs.add("tools", "ERROR", f"document_to_pdf denied: {exc}")
            raise
        except (DocumentError, PdfGenerationError) as exc:
            self._audit_pdf(
                source,
                outcome="error",
                error_category="invalid_request",
                streaming=fast,
                formatting_method="ai_structure" if ai_format else "standard",
            )
            # `exc` itself is the deliberately generic, user-facing message
            # ("No PDF was created" etc.) -- the useful diagnostic detail
            # (e.g. the specific model/provider error) lives in its __cause__
            # chain instead. Log both so a staff member checking Logs after
            # a failed PDF doesn't have to reproduce it outside the app to
            # find out why.
            self.logs.add("tools", "ERROR", f"document_to_pdf failed: {_cause_chain(exc)}")
            raise
        tool.last_status = "success"
        self._audit_pdf(
            source,
            outcome="ok",
            pages=result.pages,
            output_path=result.output_path,
            warnings=result.warnings,
            streaming=fast,
            formatting_method=result.formatting_method,
        )
        output_name = Path(result.output_path).name
        self.logs.add("tools", "INFO", f"document_to_pdf completed: {output_name}")
        return result

    def _audit_pdf(
        self,
        source: str,
        *,
        outcome: str,
        pages: int | None = None,
        output_path: str | None = None,
        error_category: str | None = None,
        warnings: list[str] | None = None,
        streaming: bool = False,
        formatting_method: str = "standard",
    ) -> None:
        summary = f"source={Path(source).name}"
        if pages is not None:
            summary += f" pages={pages}"
        if output_path is not None:
            summary += f" output={Path(output_path).name}"
        summary += f" format={'streaming' if streaming else 'standard'}"
        summary += f" formatting={formatting_method}"
        if warnings:
            summary += " notices=" + " | ".join(warnings)
        event = AuditEvent(
            user_id=self.config.user_id,
            command="pdf.create",
            request_summary=summary,
            tools_invoked=["document_to_pdf"],
            validation_result="ok" if error_category is None else "invalid",
            outcome=outcome,
            error_category=error_category,
        )
        try:
            log_event(self.base_config.audit_db_path, event)
        except (OSError, sqlite3.Error):
            self.logs.add("tools", "ERROR", "Failed to write audit log entry for pdf.create")

    def scan_document_for_calculator(
        self, source: str, field_keys: tuple[str, ...]
    ) -> dict[str, str | None]:
        """Ask the model which of `field_keys` it can find in `source`, verbatim.

        Gated by the same `documents:read` permission as `document_search` --
        reading the file is the only privileged part. The figures returned
        only ever pre-fill Calculator's own dialog fields; they are never
        computed or used directly, and the user reviews/edits them before
        anything is calculated.
        """
        tool = self.tools.get("document_search")
        try:
            self.tools.authorize_run(tool.name, self.permissions)
            complete = getattr(self.provider, "complete_document", None)
            if complete is None:
                raise ProviderError("The configured model does not support document extraction")
            content = extract_document(Path(source))
            result = extract_calculator_fields(content, field_keys, complete)
        except PermissionError as exc:
            self.logs.add("tools", "ERROR", f"calculator file scan denied: {exc}")
            raise
        except (DocumentError, ModelProviderError, ProviderError) as exc:
            self.logs.add("tools", "ERROR", f"calculator file scan failed: {exc}")
            raise
        self.logs.add("tools", "INFO", f"calculator file scan completed: {Path(source).name}")
        return result

    # -- model status -------------------------------------------------------

    def model_online(self) -> bool:
        ready_check = getattr(self.provider, "is_ready", lambda: False)
        return bool(ready_check())

    def stop(self) -> None:
        stop = getattr(self.provider, "stop", None)
        if stop is not None:
            stop()
