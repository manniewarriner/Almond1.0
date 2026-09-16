"""Branded PDF generation service: extract -> render -> verify.

Extraction/rendering are local. Callers may supply a structure formatter
before rendering (the desktop uses the shared local model). The source
document is opened read-only and is never modified, moved, or
deleted. Output never escapes the configured outputs directory, never
overwrites an existing file, and is only reported as successful once it
has been independently re-opened and verified.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel
from pypdf import PdfReader

from app.documents.content_extract import extract_document
from app.documents.content_models import DocumentContent
from app.documents.ingest import resolve_within_root
from app.errors import DocumentError, PdfGenerationError
from app.pdf.renderer import render_pdf

_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "almond-logo.png"
_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_REPEATED_DASH_RE = re.compile(r"-{2,}")
_MAX_COLLISION_ATTEMPTS = 1000


class PdfResult(BaseModel):
    """Outcome of a branded PDF generation request."""

    source_path: str
    output_path: str
    pages: int
    word_count: int
    success: bool
    warnings: list[str] = []
    formatting_method: str = "standard"


def create_branded_pdf(
    source_path: Path,
    outputs_dir: Path,
    title_override: str | None = None,
    *,
    fast: bool = False,
    page_range: tuple[int, int] | None = None,
    progress: Callable[[str], None] | None = None,
    formatter: Callable[[DocumentContent], DocumentContent] | None = None,
) -> PdfResult:
    """Extract source_path and render it as an Almond Standard Report PDF under outputs_dir.

    Raises DocumentError if the source cannot be safely read, or
    PdfGenerationError if rendering or verification fails. Never leaves a
    partially-written PDF behind on failure.
    """
    source_path = Path(source_path)
    if progress is not None:
        progress("Reading document…")
    content = extract_document(source_path, page_range=page_range, progress=progress)
    if title_override and title_override.strip():
        content = content.model_copy(update={"title": title_override.strip()})
    if formatter is not None:
        content = formatter(content)

    if not _LOGO_PATH.is_file():
        raise PdfGenerationError(f"Almond logo asset not found: {_LOGO_PATH}")

    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    filename = _collision_safe_filename(outputs_dir, _sanitize_stem(source_path.stem))
    output_path = _resolve_output_path(outputs_dir, filename)

    try:
        if progress is not None:
            progress("Rendering streaming PDF…" if fast else "Rendering branded PDF…")
        render_pdf(content, output_path, _LOGO_PATH, fast=fast, progress=progress)
    except PdfGenerationError:
        _cleanup_partial(output_path)
        raise

    if progress is not None:
        progress("Verifying output…")
    pages = _verify_pdf(output_path)

    return PdfResult(
        source_path=str(source_path),
        output_path=str(output_path),
        pages=pages,
        word_count=content.word_count,
        success=True,
        warnings=content.warnings,
        formatting_method="ai_structure" if formatter else "standard",
    )


def _sanitize_stem(stem: str) -> str:
    cleaned = _UNSAFE_CHARS_RE.sub("-", stem).strip(" .-")
    cleaned = _REPEATED_DASH_RE.sub("-", cleaned)
    return cleaned or "document"


def _collision_safe_filename(outputs_dir: Path, stem: str) -> str:
    candidate = f"{stem}-almond.pdf"
    if not (outputs_dir / candidate).exists():
        return candidate
    for suffix in range(2, _MAX_COLLISION_ATTEMPTS):
        candidate = f"{stem}-almond-{suffix}.pdf"
        if not (outputs_dir / candidate).exists():
            return candidate
    raise PdfGenerationError(f"Too many existing outputs named '{stem}-almond*.pdf'")


def _resolve_output_path(outputs_dir: Path, filename: str) -> Path:
    try:
        return resolve_within_root(outputs_dir, filename)
    except DocumentError as exc:
        raise PdfGenerationError(str(exc)) from exc


def _verify_pdf(output_path: Path) -> int:
    if not output_path.is_file() or output_path.stat().st_size == 0:
        _cleanup_partial(output_path)
        raise PdfGenerationError("Generated PDF is missing or empty")

    with output_path.open("rb") as handle:
        header = handle.read(5)
    if header != b"%PDF-":
        _cleanup_partial(output_path)
        raise PdfGenerationError("Generated file is not a valid PDF")

    try:
        reader = PdfReader(str(output_path))
        page_count = len(reader.pages)
    except Exception as exc:
        _cleanup_partial(output_path)
        raise PdfGenerationError(f"Generated PDF failed verification: {exc}") from exc

    if page_count < 1:
        _cleanup_partial(output_path)
        raise PdfGenerationError("Generated PDF has no pages")

    return page_count


def _cleanup_partial(output_path: Path) -> None:
    try:
        if output_path.exists():
            output_path.unlink()
    except OSError:
        pass
