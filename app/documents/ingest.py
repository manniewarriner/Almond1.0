"""Document ingestion: allow-listed types, path safety, checksums, chunking.

Every ingested document is untrusted reference text, never instructions.
Nothing here executes document content. Ingestion never reads outside the
configured document root (path traversal is rejected), enforces a file
size limit, and only accepts allow-listed extensions.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.documents.models import DocumentChunk, DocumentRecord
from app.errors import DocumentError

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE_CHARS = 1000


def resolve_within_root(root: Path, relative_path: str) -> Path:
    """Resolve relative_path under root, rejecting any path that escapes it."""
    resolved_root = root.resolve()
    candidate = (resolved_root / relative_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise DocumentError(f"Path escapes document root: {relative_path!r}") from exc
    return candidate


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE_CHARS) -> list[str]:
    """Deterministically split text into paragraph-aware chunks of at most chunk_size chars."""
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [text]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = [paragraph[i : i + chunk_size] for i in range(0, len(paragraph), chunk_size)]
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > chunk_size:
                chunks.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def ingest_document(root: Path, relative_path: str) -> DocumentRecord:
    path = resolve_within_root(root, relative_path)

    if not path.is_file():
        raise DocumentError(f"Document not found: {relative_path!r}")

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise DocumentError(f"File type not allowed: {path.suffix!r}")

    size_bytes = path.stat().st_size
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise DocumentError(f"File too large: {size_bytes} bytes (max {MAX_FILE_SIZE_BYTES})")

    checksum = checksum_file(path)
    doc_type = path.suffix.lower().lstrip(".")
    title = path.stem

    if doc_type == "pdf":
        chunks = _ingest_pdf(path, checksum, relative_path, title)
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        chunks = [
            DocumentChunk(
                document_id=checksum,
                filename=path.name,
                relative_path=relative_path,
                title=title,
                page=None,
                text=piece,
            )
            for piece in split_into_chunks(text)
        ]

    return DocumentRecord(
        document_id=checksum,
        filename=path.name,
        relative_path=relative_path,
        title=title,
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        doc_type=doc_type,
        chunks=chunks,
    )


def _ingest_pdf(path: Path, checksum: str, relative_path: str, title: str) -> list[DocumentChunk]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise DocumentError("pypdf is required for PDF ingestion but is not installed") from exc

    try:
        reader = PdfReader(str(path))
    except PdfReadError as exc:
        raise DocumentError(f"Failed to read PDF: {exc}") from exc

    chunks: list[DocumentChunk] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        for piece in split_into_chunks(page_text):
            chunks.append(
                DocumentChunk(
                    document_id=checksum,
                    filename=path.name,
                    relative_path=relative_path,
                    title=title,
                    page=page_number,
                    text=piece,
                )
            )
    return chunks
