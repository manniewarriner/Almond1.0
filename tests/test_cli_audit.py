"""Tests for the `firm-ai audit` CLI command and audit logging side effects
of search/ask/calc."""

from __future__ import annotations

from typer.testing import CliRunner

from app.cli import app

runner = CliRunner()


def test_audit_command_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "audit.db"))

    result = runner.invoke(app, ["audit"])

    assert result.exit_code == 0
    assert "No audit events" in result.stdout


def test_search_command_writes_audit_event(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "policy.md").write_text("KYC verification is required.", encoding="utf-8")
    audit_db = tmp_path / "audit.db"
    monkeypatch.setenv("FIRM_AI_DOCUMENTS_DIR", str(docs_dir))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(audit_db))

    runner.invoke(app, ["search", "KYC"])
    result = runner.invoke(app, ["audit"])

    assert result.exit_code == 0
    assert "search" in result.stdout


def test_denied_search_still_writes_audit_event(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    audit_db = tmp_path / "audit.db"
    monkeypatch.setenv("FIRM_AI_DOCUMENTS_DIR", str(docs_dir))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(audit_db))

    runner.invoke(app, ["search", "anything", "--user", "mallory"])
    result = runner.invoke(app, ["audit"])

    assert result.exit_code == 0
    assert "denied" in result.stdout


def test_calc_command_writes_audit_event(tmp_path, monkeypatch):
    audit_db = tmp_path / "audit.db"
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(audit_db))

    runner.invoke(app, ["calc", "percentage-return", "--start", "100", "--end", "110"])
    result = runner.invoke(app, ["audit"])

    assert result.exit_code == 0
    assert "start=100 end=110" in result.stdout
