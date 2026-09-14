"""Tests for the desktop application's UI-neutral service layer."""

from __future__ import annotations

from app.config import AppConfig
from app.desktop_service import DesktopService
from app.providers.fake import FakeProvider


def _service(tmp_path, monkeypatch) -> DesktopService:
    docs = tmp_path / "docs"
    docs.mkdir()
    users = tmp_path / "users.json"
    users.write_text(
        '{"users": [{"user_id": "local", "permissions": ["documents:read"]}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRM_AI_DOCUMENTS_DIR", str(docs))
    monkeypatch.setenv("FIRM_AI_USERS_FILE", str(users))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    return DesktopService(AppConfig(), chat_provider=FakeProvider())


def test_desktop_ask_returns_citations(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    (service.config.documents_dir / "policy.md").write_text(
        "Client onboarding requires KYC verification.", encoding="utf-8"
    )

    result = service.ask("What does onboarding require?")

    assert result.has_evidence is True
    assert result.citations == ("policy.md",)


def test_desktop_search_returns_safe_view(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    (service.config.documents_dir / "policy.md").write_text(
        "Client onboarding requires KYC verification.", encoding="utf-8"
    )

    results = service.search("KYC")

    assert len(results) == 1
    assert results[0].citation == "policy.md"
    assert "KYC" in results[0].excerpt


def test_desktop_calculator_is_deterministic(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    result = service.calculate("Percentage return", "100", "110")

    assert str(result) == "10.0"


def test_desktop_unknown_user_fails_closed(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    (service.config.documents_dir / "private.md").write_text("confidential", encoding="utf-8")

    try:
        service.search("confidential", user_id="unknown")
        raised = False
    except Exception:
        raised = True

    assert raised


def test_desktop_general_chat_uses_injected_local_provider(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    result = service.chat("Hello", [])

    assert "Hello" in result.answer
    assert result.provider_name == "fake"
