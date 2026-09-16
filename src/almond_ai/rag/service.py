from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.documents.ingest import ALLOWED_EXTENSIONS, ingest_document
from app.documents.retrieval import load_all_chunks, search_documents
from app.security.permissions import resolve_requester


@dataclass(frozen=True)
class RAGStatus:
    documents: int
    chunks: int
    database: str
    embedding_model: str
    indexing: str = "idle"
    failed_documents: int = 0
    last_index: str = "not recorded"


class RAGService:
    def __init__(self, documents_dir: Path, users_file: Path, embedding_model: str) -> None:
        self.documents_dir = documents_dir
        self.users_file = users_file
        self.embedding_model = embedding_model
        self._excluded_documents: set[str] = set()
        self._last_index = "not recorded"
        self._chunks_cache: list = []
        self._chunks_cache_signature: tuple | None = None

    def _directory_signature(self) -> tuple:
        """Cheap fingerprint of what's on disk: (relpath, mtime, size) per
        allow-listed file. Recomputing this is fast (just stat() calls); it
        lets _active_chunks() skip the expensive re-ingest (full text
        extraction, e.g. page-by-page PDF parsing) when nothing changed.
        """
        documents_dir = self.documents_dir
        if not documents_dir.is_dir():
            return ()
        return tuple(
            sorted(
                (str(path.relative_to(documents_dir)), path.stat().st_mtime_ns, path.stat().st_size)
                for path in documents_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
            )
        )

    def _all_chunks(self):
        signature = self._directory_signature()
        if signature != self._chunks_cache_signature:
            self._chunks_cache = load_all_chunks(self.documents_dir)
            self._chunks_cache_signature = signature
        return self._chunks_cache

    def _active_chunks(self):
        return [
            chunk
            for chunk in self._all_chunks()
            if chunk.document_id not in self._excluded_documents
        ]

    def status(self) -> RAGStatus:
        chunks = self._active_chunks()
        docs = len({chunk.document_id for chunk in chunks})
        return RAGStatus(
            docs,
            len(chunks),
            "local keyword index",
            self.embedding_model,
            last_index=self._last_index,
        )

    def search(self, query: str, user_id: str, top_k: int = 5):
        requester = resolve_requester(self.users_file, user_id)
        available = len(self._all_chunks())
        result = search_documents(self.documents_dir, query, requester, max(top_k, available))
        result.matches = [
            match
            for match in result.matches
            if match.chunk.document_id not in self._excluded_documents
        ][:top_k]
        return result

    def inspect(self, document: str):
        value = document.casefold()
        return [
            chunk
            for chunk in self._active_chunks()
            if value in chunk.filename.casefold() or value in chunk.document_id.casefold()
        ]

    def add(self, relative_path: str):
        """Include an existing approved-root document without copying files."""
        record = ingest_document(self.documents_dir, relative_path)
        self._excluded_documents.discard(record.document_id)
        self._last_index = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        return record

    def remove(self, document: str) -> int:
        """Exclude matching documents from this session; source files remain untouched."""
        value = document.casefold()
        matches = [
            chunk
            for chunk in self._all_chunks()
            if value in chunk.filename.casefold() or value in chunk.document_id.casefold()
        ]
        document_ids = {chunk.document_id for chunk in matches}
        if not document_ids:
            raise ValueError(f"Document not found: {document}")
        self._excluded_documents.update(document_ids)
        self._last_index = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        return len(document_ids)

    def reindex(self) -> RAGStatus:
        """Refresh index state from approved source files."""
        self._excluded_documents.clear()
        self._last_index = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        return self.status()
