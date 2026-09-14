"""Tests for app.workflows.ask: evidence-grounded, cited ask workflow."""

from __future__ import annotations

from app.documents.retrieval import REQUIRED_PERMISSION, Requester
from app.providers.fake import FakeProvider
from app.workflows.ask import ask


def _requester() -> Requester:
    return Requester(user_id="tester", permissions=frozenset({REQUIRED_PERMISSION}))


def test_ask_with_evidence(tmp_path):
    (tmp_path / "policy.md").write_text(
        "Client onboarding requires KYC verification.", encoding="utf-8"
    )

    result = ask(tmp_path, "KYC verification", _requester(), FakeProvider())

    assert result.has_evidence is True
    assert result.citations == ["policy.md"]
    assert result.answer


def test_ask_without_evidence(tmp_path):
    result = ask(tmp_path, "completely unrelated gibberish", _requester(), FakeProvider())

    assert result.has_evidence is False
    assert result.citations == []
