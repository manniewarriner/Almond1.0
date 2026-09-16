"""Structural document extraction for branded PDF generation.

Every source document is untrusted reference content, never instructions.
Nothing here executes document content, follows links, runs macros, or
runs embedded objects. Source files are opened read-only and are never
modified, moved, or deleted. This is not OCR: a PDF with no extractable
text yields a clear error instead of invented content.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from threading import RLock

from app.documents.content_models import ContentBlock, DocumentContent
from app.errors import DocumentError

ALLOWED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
MAX_SOURCE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_EXTRACTION_CACHE_ENTRIES = 8
MAX_EXTRACTION_CACHE_BYTES = 32 * 1024 * 1024

ProgressCallback = Callable[[str], None]
PageRange = tuple[int, int]
_CacheKey = tuple[str, int, int, PageRange | None, str]
_EXTRACTION_CACHE: OrderedDict[_CacheKey, bytes] = OrderedDict()
_CACHE_LOCK = RLock()
_PDFIUM_LOCK = RLock()  # PDFium calls must not overlap across threads.

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")


def extract_document(
    path: Path,
    *,
    page_range: PageRange | None = None,
    progress: ProgressCallback | None = None,
    use_cache: bool = True,
    pdf_backend: str = "pdfium",
) -> DocumentContent:
    """Validate and extract structured content from an allow-listed local file.

    Raises DocumentError (never a raw OS/parser exception) for any problem:
    missing file, wrong type, oversized file, empty file, or unreadable
    content.
    """
    if not path.exists():
        raise DocumentError(f"Document not found: {path}")
    if not path.is_file():
        raise DocumentError(f"Not a regular file: {path}")

    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise DocumentError(f"Unsupported document type: {suffix or '(none)'}")

    stat = path.stat()
    size_bytes = stat.st_size
    if size_bytes > MAX_SOURCE_SIZE_BYTES:
        raise DocumentError(f"File too large: {size_bytes} bytes (max {MAX_SOURCE_SIZE_BYTES})")
    if size_bytes == 0:
        raise DocumentError(f"Document is empty: {path.name}")

    if page_range is not None and suffix != ".pdf":
        raise DocumentError("Page selection is only available for PDF source files")
    if pdf_backend not in {"pdfium", "pypdf"}:
        raise DocumentError("Unknown PDF extraction backend")

    cache_key = (str(path.resolve()), stat.st_mtime_ns, size_bytes, page_range, pdf_backend)
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            _report_progress(progress, "Using cached document text…")
            return cached

    warnings: list[str] = []
    if suffix == ".txt":
        blocks, title = _extract_txt(path)
    elif suffix == ".md":
        blocks, title = _extract_markdown(path)
    elif suffix == ".docx":
        blocks, title = _extract_docx(path)
    elif suffix in IMAGE_EXTENSIONS:
        blocks, title, warnings = _extract_image(path)
    else:
        extractor = _extract_pdfium if pdf_backend == "pdfium" else _extract_pdf
        blocks, title, warnings = extractor(path, page_range=page_range, progress=progress)

    content = DocumentContent(
        source_path=str(path),
        title=title or path.stem,
        doc_type=suffix.lstrip("."),
        blocks=blocks,
        word_count=_count_words(blocks),
        warnings=warnings,
    )
    current_stat = path.stat()
    if use_cache and (current_stat.st_mtime_ns, current_stat.st_size) == (
        stat.st_mtime_ns,
        size_bytes,
    ):
        _cache_put(cache_key, content)
    return content


def clear_extraction_cache() -> None:
    """Clear the bounded in-memory extraction cache (primarily for tests)."""
    with _CACHE_LOCK:
        _EXTRACTION_CACHE.clear()


def _cache_get(key: _CacheKey) -> DocumentContent | None:
    with _CACHE_LOCK:
        content = _EXTRACTION_CACHE.get(key)
        if content is None:
            return None
        _EXTRACTION_CACHE.move_to_end(key)
    return DocumentContent.model_validate_json(content)


def _cache_put(key: _CacheKey, content: DocumentContent) -> None:
    # Immutable UTF-8 payloads give a measurable memory budget and isolate callers.
    payload = content.model_dump_json().encode("utf-8")
    with _CACHE_LOCK:
        _EXTRACTION_CACHE.pop(key, None)
        if len(payload) > MAX_EXTRACTION_CACHE_BYTES:
            return
        # Discard obsolete versions of this source, preserving other page selections.
        for old_key in list(_EXTRACTION_CACHE):
            if old_key[0] == key[0] and old_key[1:3] != key[1:3]:
                del _EXTRACTION_CACHE[old_key]
        _EXTRACTION_CACHE[key] = payload
        while (
            len(_EXTRACTION_CACHE) > MAX_EXTRACTION_CACHE_ENTRIES
            or sum(map(len, _EXTRACTION_CACHE.values())) > MAX_EXTRACTION_CACHE_BYTES
        ):
            _EXTRACTION_CACHE.popitem(last=False)


def _report_progress(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _count_words(blocks: list[ContentBlock]) -> int:
    total = 0
    for block in blocks:
        if block.text:
            total += len(block.text.split())
        if block.items:
            total += sum(len(item.split()) for item in block.items)
        if block.rows:
            total += sum(len(cell.split()) for row in block.rows for cell in row)
    return total


def _extract_txt(path: Path) -> tuple[list[ContentBlock], str]:
    raw = path.read_bytes()
    if b"\x00" in raw[:8192]:
        raise DocumentError(f"File does not look like text: {path.name}")

    text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        stripped = text.strip()
        paragraphs = [stripped] if stripped else []
    if not paragraphs:
        raise DocumentError(f"Document has no readable text: {path.name}")

    blocks = [ContentBlock(kind="paragraph", text=p) for p in paragraphs]
    title = paragraphs[0].splitlines()[0][:120]
    return blocks, title


def _extract_markdown(path: Path) -> tuple[list[ContentBlock], str]:
    raw = path.read_bytes()
    if b"\x00" in raw[:8192]:
        raise DocumentError(f"File does not look like text: {path.name}")
    text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    blocks: list[ContentBlock] = []
    title = ""
    paragraph_lines: list[str] = []
    list_items: list[str] | None = None
    list_ordered = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            blocks.append(ContentBlock(kind="paragraph", text=" ".join(paragraph_lines)))
            paragraph_lines = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append(ContentBlock(kind="list", ordered=list_ordered, items=list_items))
        list_items = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue

        heading_match = _HEADING_RE.match(line)
        bullet_match = _BULLET_RE.match(line)
        numbered_match = _NUMBERED_RE.match(line)

        if heading_match:
            flush_paragraph()
            flush_list()
            level = min(len(heading_match.group(1)), 3)
            heading_text = heading_match.group(2).strip()
            blocks.append(ContentBlock(kind="heading", level=level, text=heading_text))
            if not title:
                title = heading_text
        elif bullet_match:
            flush_paragraph()
            if list_items is None or list_ordered:
                flush_list()
                list_items, list_ordered = [], False
            list_items.append(bullet_match.group(1).strip())
        elif numbered_match:
            flush_paragraph()
            if list_items is None or not list_ordered:
                flush_list()
                list_items, list_ordered = [], True
            list_items.append(numbered_match.group(1).strip())
        else:
            flush_list()
            paragraph_lines.append(line)

    flush_paragraph()
    flush_list()

    if not blocks:
        raise DocumentError(f"Document has no readable text: {path.name}")

    return blocks, title


def _extract_docx(path: Path) -> tuple[list[ContentBlock], str]:
    try:
        from docx import Document
    except ImportError as exc:
        raise DocumentError("python-docx is required for DOCX extraction") from exc

    try:
        document = Document(str(path))
    except Exception as exc:  # python-docx raises varied errors on corrupt/foreign files
        raise DocumentError(f"Failed to read DOCX: {exc}") from exc

    blocks: list[ContentBlock] = []
    list_items: list[str] | None = None
    list_ordered = False

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append(ContentBlock(kind="list", ordered=list_ordered, items=list_items))
        list_items = None

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        style_name = paragraph.style.name if paragraph.style else ""
        if not text:
            flush_list()
            continue

        if style_name.startswith("Heading"):
            flush_list()
            digits = "".join(ch for ch in style_name if ch.isdigit())
            level = min(int(digits), 3) if digits else 1
            blocks.append(ContentBlock(kind="heading", level=level, text=text))
        elif style_name.startswith("List Bullet"):
            if list_items is None or list_ordered:
                flush_list()
                list_items, list_ordered = [], False
            list_items.append(text)
        elif style_name.startswith("List Number"):
            if list_items is None or not list_ordered:
                flush_list()
                list_items, list_ordered = [], True
            list_items.append(text)
        else:
            flush_list()
            blocks.append(ContentBlock(kind="paragraph", text=text))
    flush_list()

    for table in document.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        rows = [row for row in rows if any(cell for cell in row)]
        if rows:
            blocks.append(ContentBlock(kind="table", rows=rows))

    if not blocks:
        raise DocumentError(f"Document has no readable text: {path.name}")

    title = ""
    try:
        title = (document.core_properties.title or "").strip()
    except Exception:
        title = ""
    if not title:
        title = next((b.text for b in blocks if b.kind == "heading" and b.text), "")

    return blocks, title


_TESSERACT_CMD = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def _extract_image(path: Path) -> tuple[list[ContentBlock], str, list[str]]:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise DocumentError("pytesseract and Pillow are required for image OCR") from exc

    if _TESSERACT_CMD.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(_TESSERACT_CMD)

    try:
        image = Image.open(path)
        image.load()
    except Exception as exc:  # Pillow raises varied errors on corrupt/foreign files
        raise DocumentError(f"Failed to read image: {exc}") from exc

    try:
        raw_text = pytesseract.image_to_string(image)
    except Exception as exc:
        raise DocumentError(f"OCR failed: {exc}") from exc

    paragraphs = [p.strip() for p in raw_text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    if not paragraphs:
        stripped = raw_text.strip()
        paragraphs = [stripped] if stripped else []

    warnings: list[str] = []
    if not paragraphs:
        warnings.append("OCR found no readable text in this image.")
        blocks = [ContentBlock(kind="paragraph", text="(No text detected by OCR.)")]
    else:
        blocks = [ContentBlock(kind="paragraph", text=p) for p in paragraphs]

    title = paragraphs[0].splitlines()[0][:120] if paragraphs else path.stem
    return blocks, title, warnings


def _extract_pdf(
    path: Path,
    page_range: PageRange | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[list[ContentBlock], str, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentError("pypdf is required for PDF extraction") from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf raises several distinct error types on bad input
        raise DocumentError(f"Failed to read PDF: {exc}") from exc

    if reader.is_encrypted:
        raise DocumentError(f"PDF is password-protected: {path.name}")

    total_pages = len(reader.pages)
    if total_pages < 1:
        raise DocumentError(f"PDF has no pages: {path.name}")

    start_page, end_page = page_range or (1, total_pages)
    if start_page < 1 or end_page < start_page or start_page > total_pages:
        raise DocumentError(f"Invalid PDF page range: {start_page}-{end_page}")
    end_page = min(end_page, total_pages)

    blocks: list[ContentBlock] = []
    selected_count = end_page - start_page + 1
    for selected_index, page_number in enumerate(range(start_page, end_page + 1), start=1):
        if selected_index == 1 or selected_index % 25 == 0 or selected_index == selected_count:
            _report_progress(progress, f"Extracting page {selected_index} of {selected_count}…")
        page = reader.pages[page_number - 1]
        try:
            page_text = (page.extract_text() or "").strip()
        except Exception:
            page_text = ""
        for paragraph in [p.strip() for p in page_text.split("\n\n") if p.strip()]:
            blocks.append(ContentBlock(kind="paragraph", text=paragraph))

    if not blocks:
        raise DocumentError(
            "PDF contains no extractable text. OCR is not available in this version."
        )

    title = ""
    try:
        meta_title = reader.metadata.title if reader.metadata else None
        if meta_title:
            title = str(meta_title).strip()
    except Exception:
        title = ""

    warnings = []
    if page_range is not None and (start_page != 1 or end_page != total_pages):
        warnings.append(f"Included source pages {start_page}–{end_page} of {total_pages}.")

    return blocks, title, warnings


def _extract_pdfium(
    path: Path,
    page_range: PageRange | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[list[ContentBlock], str, list[str]]:
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    # Preserve the existing policy: reject encrypted files even with an empty password.
    try:
        with path.open("rb") as handle:
            encrypted = PdfReader(handle).is_encrypted
    except Exception as exc:
        raise DocumentError("Failed to read PDF") from exc
    if encrypted:
        raise DocumentError(f"PDF is password-protected: {path.name}")

    blocks: list[ContentBlock] = []
    with _PDFIUM_LOCK:
        try:
            with pdfium.PdfDocument(str(path)) as document:
                total = len(document)
                start, end = page_range or (1, total)
                if total < 1 or start < 1 or end < start or start > total:
                    raise DocumentError(f"Invalid PDF page range: {start}-{end}")
                end = min(end, total)
                title = document.get_metadata_value("Title").strip()
                for index in range(start - 1, end):
                    if index == start - 1 or (index - start + 2) % 25 == 0 or index == end - 1:
                        _report_progress(
                            progress, f"Extracting page {index - start + 2} of {end - start + 1}…"
                        )
                    page = document[index]
                    try:
                        text_page = page.get_textpage()
                        try:
                            text = text_page.get_text_bounded().replace("\r\n", "\n").strip()
                        finally:
                            text_page.close()
                    finally:
                        page.close()
                    blocks.extend(
                        ContentBlock(kind="paragraph", text=paragraph.strip())
                        for paragraph in text.split("\n\n")
                        if paragraph.strip()
                    )
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("Failed to extract PDF text") from exc
    if not blocks:
        raise DocumentError(
            "PDF contains no extractable text. OCR is not available in this version."
        )
    warnings = []
    if start != 1 or end != total:
        warnings.append(f"Included source pages {start}–{end} of {total}.")
    return blocks, title, warnings
