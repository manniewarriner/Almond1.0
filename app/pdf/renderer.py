"""Almond Standard Report: deterministic PDF rendering with ReportLab.

No browser, no cloud rendering service, no model inference. Content flows
through ReportLab's platypus layer so pagination, paragraph wrapping, and
table wrapping are handled deterministically from the extracted
DocumentContent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as canvas_module
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.documents.content_models import ContentBlock, DocumentContent
from app.errors import PdfGenerationError
from app.pdf import styles

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 2.0 * cm
FIRST_HEADER_HEIGHT = 3.6 * cm
LATER_HEADER_HEIGHT = 1.6 * cm
FOOTER_RESERVE = 1.1 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

_HEADING_STYLES = {
    1: ParagraphStyle(
        "AlmondH1",
        fontName=styles.FONT_BOLD,
        fontSize=styles.SIZE_H1,
        leading=styles.SIZE_H1 * 1.25,
        textColor=styles.COLOR_CHARCOAL,
        spaceBefore=14,
        spaceAfter=8,
        alignment=TA_LEFT,
    ),
    2: ParagraphStyle(
        "AlmondH2",
        fontName=styles.FONT_BOLD,
        fontSize=styles.SIZE_H2,
        leading=styles.SIZE_H2 * 1.25,
        textColor=styles.COLOR_CHARCOAL,
        spaceBefore=12,
        spaceAfter=6,
        alignment=TA_LEFT,
    ),
    3: ParagraphStyle(
        "AlmondH3",
        fontName=styles.FONT_BOLD,
        fontSize=styles.SIZE_H3,
        leading=styles.SIZE_H3 * 1.25,
        textColor=styles.COLOR_CHARCOAL,
        spaceBefore=10,
        spaceAfter=5,
        alignment=TA_LEFT,
    ),
}

_BODY_STYLE = ParagraphStyle(
    "AlmondBody",
    fontName=styles.FONT_REGULAR,
    fontSize=styles.SIZE_BODY,
    leading=14,
    textColor=styles.COLOR_CHARCOAL,
    spaceAfter=8,
    alignment=TA_LEFT,
)

_LIST_ITEM_STYLE = ParagraphStyle(
    "AlmondListItem",
    fontName=styles.FONT_REGULAR,
    fontSize=styles.SIZE_BODY,
    leading=13,
    textColor=styles.COLOR_CHARCOAL,
)

_TABLE_CELL_STYLE = ParagraphStyle(
    "AlmondTableCell",
    fontName=styles.FONT_REGULAR,
    fontSize=9,
    leading=11,
    textColor=styles.COLOR_CHARCOAL,
)

_TABLE_HEADER_STYLE = ParagraphStyle(
    "AlmondTableHeader",
    fontName=styles.FONT_BOLD,
    fontSize=9,
    leading=11,
    textColor=styles.COLOR_CHARCOAL,
)

_TITLE_STYLE = ParagraphStyle(
    "AlmondTitle",
    fontName=styles.FONT_BOLD,
    fontSize=styles.SIZE_TITLE,
    leading=styles.SIZE_TITLE * 1.25,
    textColor=styles.COLOR_CHARCOAL,
    spaceAfter=6,
)

_META_STYLE = ParagraphStyle(
    "AlmondMeta",
    fontName=styles.FONT_REGULAR,
    fontSize=styles.SIZE_SMALL + 1,
    leading=(styles.SIZE_SMALL + 1) * 1.3,
    textColor=styles.COLOR_MUTED,
    spaceAfter=2,
)


class _NumberedCanvas(canvas_module.Canvas):
    """Buffers pages so the footer can show 'Page X of Y' once the total is known."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, total_pages: int) -> None:
        self.setFont(styles.FONT_REGULAR, styles.SIZE_SMALL)
        self.setFillColor(styles.COLOR_MUTED)
        self.drawRightString(
            PAGE_WIDTH - MARGIN, MARGIN * 0.4, f"Page {self.getPageNumber()} of {total_pages}"
        )


class _StreamingCanvas(canvas_module.Canvas):
    """Writes each page immediately, avoiding the standard mode's page replay."""

    def __init__(self, *args, progress: Callable[[str], None] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._progress = progress

    def showPage(self) -> None:
        page_number = self.getPageNumber()
        self.setFont(styles.FONT_REGULAR, styles.SIZE_SMALL)
        self.setFillColor(styles.COLOR_MUTED)
        self.drawRightString(PAGE_WIDTH - MARGIN, MARGIN * 0.4, f"Page {page_number}")
        if self._progress is not None and (page_number == 1 or page_number % 25 == 0):
            self._progress(f"Rendered page {page_number}…")
        super().showPage()


def _draw_logo(
    canvas_obj, logo_reader: ImageReader | None, x: float, top_y: float, max_h: float
) -> None:
    if logo_reader is None:
        return
    iw, ih = logo_reader.getSize()
    if iw <= 0 or ih <= 0:
        return
    height = max_h
    width = height * (iw / ih)
    canvas_obj.drawImage(
        logo_reader,
        x,
        top_y - height,
        width=width,
        height=height,
        mask="auto",
        preserveAspectRatio=True,
    )


def _safe_markup(text: str) -> str:
    """Escape user-supplied text so it is safe inside ReportLab's mini-XML markup."""
    return _xml_escape(text).replace("\n", "<br/>")


def _draw_footer(canvas_obj) -> None:
    canvas_obj.setFont(styles.FONT_REGULAR, styles.SIZE_SMALL)
    canvas_obj.setFillColor(styles.COLOR_MUTED)
    canvas_obj.drawString(MARGIN, MARGIN * 0.4, "Almond Financial | Internal Use")


def _make_first_page_drawer(logo_reader):
    def draw(canvas_obj, _doc) -> None:
        canvas_obj.saveState()
        canvas_obj.setFillColor(styles.COLOR_HEADER_BAND)
        canvas_obj.rect(
            0, PAGE_HEIGHT - FIRST_HEADER_HEIGHT, PAGE_WIDTH, FIRST_HEADER_HEIGHT, fill=1, stroke=0
        )
        _draw_logo(
            canvas_obj,
            logo_reader,
            MARGIN,
            PAGE_HEIGHT - 0.5 * cm,
            FIRST_HEADER_HEIGHT - 1.0 * cm,
        )
        canvas_obj.setFillColor(styles.COLOR_ORANGE)
        canvas_obj.rect(
            0,
            PAGE_HEIGHT - FIRST_HEADER_HEIGHT - 0.12 * cm,
            PAGE_WIDTH,
            0.12 * cm,
            fill=1,
            stroke=0,
        )
        _draw_footer(canvas_obj)
        canvas_obj.restoreState()

    return draw


def _make_later_page_drawer(logo_reader):
    def draw(canvas_obj, _doc) -> None:
        canvas_obj.saveState()
        canvas_obj.setFillColor(styles.COLOR_HEADER_BAND)
        canvas_obj.rect(
            0, PAGE_HEIGHT - LATER_HEADER_HEIGHT, PAGE_WIDTH, LATER_HEADER_HEIGHT, fill=1, stroke=0
        )
        _draw_logo(
            canvas_obj,
            logo_reader,
            MARGIN,
            PAGE_HEIGHT - 0.25 * cm,
            LATER_HEADER_HEIGHT - 0.5 * cm,
        )
        _draw_footer(canvas_obj)
        canvas_obj.restoreState()

    return draw


def _list_flowable(block: ContentBlock) -> Table:
    """Render a list as a borderless two-column table (marker | text).

    Deliberately avoids ReportLab's ListFlowable bullet/number glyphs, which
    render unreliably across environments; explicit marker text is simple
    and deterministic instead.
    """
    items = block.items or []
    marker_width = 22 if block.ordered else 14
    rows = [
        [
            Paragraph(f"{i}." if block.ordered else "•", _LIST_ITEM_STYLE),
            Paragraph(_safe_markup(item), _LIST_ITEM_STYLE),
        ]
        for i, item in enumerate(items, start=1)
    ]
    table = Table(rows, colWidths=[marker_width, CONTENT_WIDTH - marker_width])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _table_flowable(block: ContentBlock) -> Table:
    rows = block.rows or []
    if not rows:
        raise PdfGenerationError("Table block has no rows")
    col_count = max(len(row) for row in rows)
    col_width = CONTENT_WIDTH / col_count

    def cell(text: str, is_header: bool) -> Paragraph:
        style = _TABLE_HEADER_STYLE if is_header else _TABLE_CELL_STYLE
        return Paragraph(_safe_markup(text) if text else "", style)

    data = []
    for row_index, row in enumerate(rows):
        padded = list(row) + [""] * (col_count - len(row))
        data.append([cell(value, row_index == 0) for value in padded])

    table = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), styles.COLOR_TABLE_HEADER_BG),
                ("GRID", (0, 0), (-1, -1), 0.5, styles.COLOR_TABLE_GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _build_flowables(blocks: list[ContentBlock]) -> list:
    flowables: list = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.kind == "heading":
            heading = Paragraph(
                _safe_markup(block.text or ""),
                _HEADING_STYLES.get(block.level or 1, _HEADING_STYLES[3]),
            )
            next_block = blocks[index + 1] if index + 1 < len(blocks) else None
            if next_block is not None and next_block.kind in {"paragraph", "list"}:
                flowables.append(KeepTogether([heading, _render_block(next_block)]))
                index += 2
            else:
                flowables.append(heading)
                index += 1
            continue
        flowables.append(_render_block(block))
        index += 1
    return flowables


def _render_block(block: ContentBlock):
    if block.kind == "heading":
        return Paragraph(
            _safe_markup(block.text or ""),
            _HEADING_STYLES.get(block.level or 1, _HEADING_STYLES[3]),
        )
    if block.kind == "paragraph":
        return Paragraph(_safe_markup(block.text or ""), _BODY_STYLE)
    if block.kind == "list":
        return _list_flowable(block)
    if block.kind == "table":
        return _table_flowable(block)
    raise PdfGenerationError(f"Unknown content block kind: {block.kind}")


def render_pdf(
    content: DocumentContent,
    output_path: Path,
    logo_path: Path,
    *,
    fast: bool = False,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Render content as an Almond Standard Report PDF at output_path.

    Deterministic and fully local: no network access, no model inference.
    Raises PdfGenerationError on any rendering failure.
    """
    try:
        logo_reader = ImageReader(str(logo_path)) if logo_path.is_file() else None
    except Exception as exc:
        raise PdfGenerationError(f"Failed to load Almond logo: {exc}") from exc

    generated_on = datetime.now(UTC).strftime("%Y-%m-%d")
    source_name = Path(content.source_path).name

    try:
        doc = BaseDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN + FOOTER_RESERVE,
            title=f"{content.title} - Almond Financial",
            author="Almond Financial",
        )

        first_frame = Frame(
            MARGIN,
            MARGIN + FOOTER_RESERVE,
            CONTENT_WIDTH,
            PAGE_HEIGHT - 2 * MARGIN - FOOTER_RESERVE - FIRST_HEADER_HEIGHT,
            id="first",
        )
        later_frame = Frame(
            MARGIN,
            MARGIN + FOOTER_RESERVE,
            CONTENT_WIDTH,
            PAGE_HEIGHT - 2 * MARGIN - FOOTER_RESERVE - LATER_HEADER_HEIGHT,
            id="later",
        )

        doc.addPageTemplates(
            [
                PageTemplate(
                    id="First",
                    frames=[first_frame],
                    onPage=_make_first_page_drawer(logo_reader),
                ),
                PageTemplate(
                    id="Later", frames=[later_frame], onPage=_make_later_page_drawer(logo_reader)
                ),
            ]
        )

        title_block = [
            Paragraph(_safe_markup(content.title), _TITLE_STYLE),
            Paragraph(
                _safe_markup(f"Source: {source_name}  |  Generated: {generated_on}"), _META_STYLE
            ),
            Spacer(1, 10),
        ]
        notices = [
            Paragraph(
                _safe_markup(
                    f"EXCERPT — {warning}"
                    if warning.startswith("Included source pages")
                    else warning
                ),
                _META_STYLE,
            )
            for warning in content.warnings
        ]
        story = [
            NextPageTemplate("Later"),
            *title_block,
            *notices,
            *_build_flowables(content.blocks),
        ]

        canvas_maker = partial(_StreamingCanvas, progress=progress) if fast else _NumberedCanvas
        doc.build(story, canvasmaker=canvas_maker)
    except PdfGenerationError:
        raise
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render PDF: {exc}") from exc
