"""Local keyword-based retrieval with citations.

No vector database, per project defaults: this ranks document chunks by
simple term-overlap with the query. Access scope is enforced before any
chunk is returned. Every result carries citation metadata (filename,
relative path, page); an empty result set is reported explicitly rather
than papered over.

Known limitation (documented, not hidden): this does not detect
*conflicting* evidence across chunks -- that requires semantic
comparison, which belongs in the Phase 5 ask workflow, not in raw
keyword retrieval.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from app.documents.ingest import ALLOWED_EXTENSIONS, ingest_document
from app.documents.models import DocumentChunk
from app.errors import PermissionDeniedError, RetrievalError

_WORD_RE = re.compile(r"[a-z0-9]+")

REQUIRED_PERMISSION = "documents:read"


class Requester(BaseModel):
    user_id: str
    permissions: frozenset[str] = frozenset()


class RetrievedChunk(BaseModel):
    chunk: DocumentChunk
    score: float


class RetrievalResult(BaseModel):
    query: str
    matches: list[RetrievedChunk]

    @property
    def has_evidence(self) -> bool:
        return len(self.matches) > 0


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _score(query_tokens: list[str], chunk_text: str) -> float:
    chunk_tokens = _tokenize(chunk_text)
    if not chunk_tokens:
        return 0.0
    counts: dict[str, int] = {}
    for token in chunk_tokens:
        counts[token] = counts.get(token, 0) + 1
    overlap = sum(counts.get(token, 0) for token in query_tokens)
    return overlap / len(chunk_tokens)


def load_all_chunks(documents_dir: Path) -> list[DocumentChunk]:
    """Ingest every allow-listed file under documents_dir."""
    documents_dir = documents_dir.resolve()
    if not documents_dir.is_dir():
        return []

    chunks: list[DocumentChunk] = []
    for path in sorted(documents_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        relative_path = str(path.relative_to(documents_dir))
        record = ingest_document(documents_dir, relative_path)
        chunks.extend(record.chunks)
    return chunks


def search_documents(
    documents_dir: Path,
    query: str,
    requester: Requester,
    top_k: int = 5,
) -> RetrievalResult:
    if REQUIRED_PERMISSION not in requester.permissions:
        raise PermissionDeniedError(
            f"{requester.user_id!r} lacks permission {REQUIRED_PERMISSION!r} for document search"
        )

    query = query.strip()
    if not query:
        raise RetrievalError("query must not be empty")

    query_tokens = _tokenize(query)
    if not query_tokens:
        raise RetrievalError("query has no searchable terms")

    chunks = load_all_chunks(documents_dir)

    scored = [
        RetrievedChunk(chunk=chunk, score=_score(query_tokens, chunk.text)) for chunk in chunks
    ]
    scored = [item for item in scored if item.score > 0]
    scored.sort(key=lambda item: (-item.score, item.chunk.relative_path, item.chunk.page or 0))

    return RetrievalResult(query=query, matches=scored[:top_k])


def format_citation(chunk: DocumentChunk) -> str:
    if chunk.page is not None:
        return f"{chunk.filename} (page {chunk.page})"
    return chunk.filename
