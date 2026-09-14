"""Document and chunk metadata models."""

from __future__ import annotations

from pydantic import BaseModel


class DocumentChunk(BaseModel):
    document_id: str
    filename: str
    relative_path: str
    title: str
    page: int | None = None
    text: str


class DocumentRecord(BaseModel):
    document_id: str
    filename: str
    relative_path: str
    title: str
    checksum_sha256: str
    size_bytes: int
    doc_type: str
    chunks: list[DocumentChunk]
