"""Tests for app.documents.retrieval: permission gate, ranking, citations."""

from __future__ import annotations

import pytest

from app.documents.retrieval import (
    REQUIRED_PERMISSION,
    Requester,
    format_citation,
    load_all_chunks,
    search_documents,
)
from app.errors import PermissionDeniedError, RetrievalError


def _requester(*, granted: bool = True) -> Requester:
    perms = frozenset({REQUIRED_PERMISSION}) if granted else frozenset()
    return Requester(user_id="tester", permissions=perms)


def test_search_denies_without_permission(tmp_path):
    with pytest.raises(PermissionDeniedError):
        search_documents(tmp_path, "kyc", _requester(granted=False))


def test_search_rejects_empty_query(tmp_path):
    with pytest.raises(RetrievalError):
        search_documents(tmp_path, "   ", _requester())


def test_search_no_evidence_for_unmatched_query(tmp_path):
    (tmp_path / "policy.md").write_text("Onboarding requires KYC verification.", encoding="utf-8")

    result = search_documents(tmp_path, "unrelated gibberish term", _requester())

    assert result.has_evidence is False
    assert result.matches == []


def test_search_ranks_matching_chunk(tmp_path):
    (tmp_path / "policy.md").write_text("Onboarding requires KYC verification.", encoding="utf-8")
    (tmp_path / "other.md").write_text("Unrelated content about office hours.", encoding="utf-8")

    result = search_documents(tmp_path, "KYC verification", _requester())

    assert result.has_evidence is True
    assert result.matches[0].chunk.filename == "policy.md"


def test_load_all_chunks_across_multiple_files(tmp_path):
    (tmp_path / "a.txt").write_text("Alpha content.", encoding="utf-8")
    (tmp_path / "b.md").write_text("Beta content.", encoding="utf-8")
    (tmp_path / "ignored.exe").write_bytes(b"binary")

    chunks = load_all_chunks(tmp_path)

    filenames = {chunk.filename for chunk in chunks}
    assert filenames == {"a.txt", "b.md"}


def test_load_all_chunks_missing_dir(tmp_path):
    assert load_all_chunks(tmp_path / "does-not-exist") == []


def test_format_citation_with_page(tmp_path):
    (tmp_path / "doc.md").write_text("Some content.", encoding="utf-8")
    result = search_documents(tmp_path, "content", _requester())
    citation = format_citation(result.matches[0].chunk)

    assert citation == "doc.md"
