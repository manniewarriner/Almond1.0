"""UI-neutral application service for Almond's desktop interface."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from app.audit.log import AuditEvent, log_event, read_recent_events
from app.config import AppConfig, load_config
from app.documents.retrieval import format_citation, search_documents
from app.health import run_health_check
from app.local_model import LocalModelServer
from app.providers.base import Provider, ProviderMessage
from app.providers.factory import get_provider
from app.providers.llama_cpp import LlamaCppProvider
from app.security.permissions import resolve_requester
from app.tools.calculator import absolute_change, percentage_return, to_decimal
from app.workflows.ask import ask
from app.workflows.chat import chat


@dataclass(frozen=True)
class AnswerView:
    answer: str
    citations: tuple[str, ...]
    has_evidence: bool


@dataclass(frozen=True)
class SearchView:
    score: float
    citation: str
    excerpt: str


@dataclass(frozen=True)
class ChatView:
    answer: str
    provider_name: str


class DesktopService:
    """Expose only Almond's allow-listed, non-autonomous operations."""

    def __init__(
        self,
        config: AppConfig | None = None,
        chat_provider: Provider | None = None,
    ) -> None:
        self.config = config or load_config()
        self.local_model_server = None
        if chat_provider is None:
            self.local_model_server = LocalModelServer(self.config.local_chat_model)
            chat_provider = LlamaCppProvider(self.local_model_server)
        self.chat_provider = chat_provider

    def start_local_model(self) -> str:
        if self.local_model_server is None:
            return self.chat_provider.name
        self.local_model_server.start()
        return f"Ready • {self.config.local_chat_model} • Local only"

    def stop_local_model(self) -> None:
        if self.local_model_server is not None:
            self.local_model_server.stop()

    def _requester(self, user_id: str):
        return resolve_requester(self.config.users_file, user_id.strip() or "local")

    def _audit(
        self,
        user_id: str,
        command: str,
        request_summary: str,
        *,
        outcome: str,
        document_ids: list[str] | None = None,
        tools_invoked: list[str] | None = None,
        error_category: str | None = None,
    ) -> None:
        event = AuditEvent(
            user_id=user_id,
            command=command,
            request_summary=request_summary,
            document_ids=document_ids or [],
            tools_invoked=tools_invoked or [],
            validation_result="ok" if error_category is None else "invalid",
            outcome=outcome,
            error_category=error_category,
        )
        try:
            log_event(self.config.audit_db_path, event)
        except (OSError, sqlite3.Error):
            pass

    def ask(self, question: str, user_id: str = "local", top_k: int = 5) -> AnswerView:
        question = question.strip()
        provider = get_provider(self.config)
        requester = self._requester(user_id)
        try:
            result = ask(self.config.documents_dir, question, requester, provider, top_k=top_k)
        except Exception as exc:
            self._audit(
                user_id,
                "desktop.ask",
                question,
                outcome="error",
                error_category=type(exc).__name__,
            )
            raise
        self._audit(
            user_id,
            "desktop.ask",
            question,
            outcome="ok",
            document_ids=list(result.citations),
            tools_invoked=[f"provider:{provider.name}"],
        )
        return AnswerView(result.answer, tuple(result.citations), result.has_evidence)

    def chat(
        self,
        message: str,
        history: list[ProviderMessage],
        user_id: str = "local",
    ) -> ChatView:
        try:
            result = chat(message, history, self.chat_provider)
        except Exception as exc:
            self._audit(
                user_id,
                "desktop.chat",
                f"message_length={len(message)}",
                outcome="error",
                error_category=type(exc).__name__,
            )
            raise
        self._audit(
            user_id,
            "desktop.chat",
            f"message_length={len(message)}",
            outcome="ok",
            tools_invoked=[f"provider:{result.provider_name}"],
        )
        return ChatView(result.answer, result.provider_name)

    def search(self, query: str, user_id: str = "local", top_k: int = 5) -> list[SearchView]:
        query = query.strip()
        requester = self._requester(user_id)
        try:
            result = search_documents(self.config.documents_dir, query, requester, top_k=top_k)
        except Exception as exc:
            self._audit(
                user_id,
                "desktop.search",
                query,
                outcome="error",
                error_category=type(exc).__name__,
            )
            raise
        ids = [match.chunk.document_id for match in result.matches]
        self._audit(user_id, "desktop.search", query, outcome="ok", document_ids=ids)
        return [
            SearchView(
                score=match.score,
                citation=format_citation(match.chunk),
                excerpt=match.chunk.text[:300].replace("\n", " "),
            )
            for match in result.matches
        ]

    def calculate(self, kind: str, start: str, end: str, user_id: str = "local") -> Decimal:
        start_value = to_decimal(start)
        end_value = to_decimal(end)
        if kind == "Percentage return":
            result = percentage_return(start_value, end_value)
            command = "desktop.calc.percentage-return"
        elif kind == "Absolute change":
            result = absolute_change(start_value, end_value)
            command = "desktop.calc.absolute-change"
        else:
            raise ValueError("Unknown calculation type")
        self._audit(user_id, command, f"start={start} end={end}", outcome="ok")
        return result

    def recent_audit_events(self, limit: int = 50) -> list[dict]:
        return read_recent_events(self.config.audit_db_path, limit=limit)

    def health_items(self):
        return run_health_check().items
