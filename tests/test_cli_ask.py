"""Tests for the `firm-ai ask` CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from app.cli import app

runner = CliRunner()


def test_ask_command_with_evidence(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "policy.md").write_text(
        "Client onboarding requires KYC verification.", encoding="utf-8"
    )
    monkeypatch.setenv("FIRM_AI_DOCUMENTS_DIR", str(docs_dir))

    result = runner.invoke(app, ["ask", "KYC verification"])

    assert result.exit_code == 0
    assert "policy.md" in result.stdout


def test_ask_command_without_evidence(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    monkeypatch.setenv("FIRM_AI_DOCUMENTS_DIR", str(docs_dir))

    result = runner.invoke(app, ["ask", "totally unrelated question"])

    assert result.exit_code == 0
    assert "No approved-document evidence" in result.stdout


def test_ask_command_empty_question(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_DOCUMENTS_DIR", str(tmp_path))

    result = runner.invoke(app, ["ask", "   "])

    assert result.exit_code == 1


def test_ask_command_unknown_user_denied(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "policy.md").write_text("Client onboarding requires KYC.", encoding="utf-8")
    monkeypatch.setenv("FIRM_AI_DOCUMENTS_DIR", str(docs_dir))

    result = runner.invoke(app, ["ask", "KYC", "--user", "mallory"])

    assert result.exit_code == 1
    assert "Ask error" in result.stdout
    assert "policy.md" not in result.stdout
