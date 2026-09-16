"""Structural content models for branded PDF generation.

Distinct from app.documents.models (which chunks text for RAG retrieval):
these preserve heading levels, paragraph order, lists, and tables so a
document can be rendered back out with its structure intact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ContentBlock(BaseModel):
    """One structural unit of a document, in original reading order."""

    kind: Literal["heading", "paragraph", "list", "table"]
    level: int | None = None  # heading only: 1, 2, or 3
    text: str | None = None  # heading / paragraph only
    items: list[str] | None = None  # list only
    ordered: bool | None = None  # list only
    rows: list[list[str]] | None = None  # table only


class DocumentContent(BaseModel):
    """Structured, extracted content of one source document."""

    source_path: str
    title: str
    doc_type: str
    blocks: list[ContentBlock]
    word_count: int
    warnings: list[str] = []
