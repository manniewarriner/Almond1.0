"""Tests for app.documents.ingest: allow-listing, path safety, checksums, chunking."""

from __future__ import annotations

import pytest

from app.documents import ingest as ingest_module
from app.documents.ingest import ingest_document, resolve_within_root, split_into_chunks
from app.errors import DocumentError


def test_resolve_within_root_ok(tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")

    resolved = resolve_within_root(tmp_path, "a.txt")

    assert resolved == (tmp_path / "a.txt").resolve()


def test_resolve_within_root_rejects_traversal(tmp_path):
    with pytest.raises(DocumentError):
        resolve_within_root(tmp_path, "../outside.txt")


def test_ingest_missing_file(tmp_path):
    with pytest.raises(DocumentError):
        ingest_document(tmp_path, "missing.txt")


def test_ingest_disallowed_extension(tmp_path):
    (tmp_path / "script.exe").write_bytes(b"binary")

    with pytest.raises(DocumentError):
        ingest_document(tmp_path, "script.exe")


def test_ingest_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_module, "MAX_FILE_SIZE_BYTES", 10)
    (tmp_path / "big.txt").write_text("x" * 100, encoding="utf-8")

    with pytest.raises(DocumentError):
        ingest_document(tmp_path, "big.txt")


def test_ingest_text_document(tmp_path):
    (tmp_path / "notes.txt").write_text("Paragraph one.\n\nParagraph two.", encoding="utf-8")

    record = ingest_document(tmp_path, "notes.txt")

    assert record.doc_type == "txt"
    assert record.filename == "notes.txt"
    assert record.title == "notes"
    assert len(record.checksum_sha256) == 64
    assert len(record.chunks) == 1
    assert "Paragraph one." in record.chunks[0].text
    assert record.chunks[0].page is None


def test_ingest_strips_utf8_bom(tmp_path):
    (tmp_path / "bom.txt").write_bytes(b"\xef\xbb\xbfHello world.")

    record = ingest_document(tmp_path, "bom.txt")

    assert record.chunks[0].text == "Hello world."


def test_ingest_markdown_document(tmp_path):
    (tmp_path / "doc.md").write_text("# Title\n\nSome content here.", encoding="utf-8")

    record = ingest_document(tmp_path, "doc.md")

    assert record.doc_type == "md"
    assert len(record.chunks) >= 1


def test_ingest_pdf_blank_page(tmp_path):
    from pypdf import PdfWriter

    pdf_path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    record = ingest_document(tmp_path, "doc.pdf")

    assert record.doc_type == "pdf"
    assert record.chunks == []


def test_split_into_chunks_respects_size():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 50 for i in range(5))

    chunks = split_into_chunks(text, chunk_size=200)

    assert all(len(chunk) <= 200 for chunk in chunks)
    assert len(chunks) > 1


def test_split_into_chunks_empty_text():
    assert split_into_chunks("   ") == []
