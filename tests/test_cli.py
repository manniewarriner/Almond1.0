"""Tests for the Typer CLI: help text, health command exit codes, error handling."""

from __future__ import annotations

from typer.testing import CliRunner

from app.cli import app
from app.models import CheckStatus, HealthCheckItem, HealthReport

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "health" in result.stdout


def test_cli_health_success(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "data" / "audit.db"))

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0
    assert "ok" in result.stdout


def test_cli_health_failure_exit_code():
    result = runner.invoke(app, ["health", "--env-file", "does-not-exist.env"])

    assert result.exit_code == 1
    assert "fail" in result.stdout


def test_cli_health_unexpected_error(monkeypatch):
    def boom(env_file=None):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr("app.cli.run_health_check", boom)

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 2
    assert "Unexpected error" in result.stdout
    assert "Traceback" not in result.stdout


def test_health_report_ok_property():
    ok_report = HealthReport(
        items=[HealthCheckItem(name="x", status=CheckStatus.OK, detail="fine")]
    )
    fail_report = HealthReport(
        items=[HealthCheckItem(name="x", status=CheckStatus.FAIL, detail="bad")]
    )

    assert ok_report.ok is True
    assert fail_report.ok is False
