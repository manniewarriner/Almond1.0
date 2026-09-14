"""Tests for app.health: config, directories, audit db, provider syntax checks."""

from __future__ import annotations

from app.health import run_health_check
from app.models import CheckStatus


def test_health_check_success(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "data" / "audit.db"))

    report = run_health_check()

    assert report.ok
    names = {item.name for item in report.items}
    assert names == {"config", "data_dir", "audit_db", "provider_config"}
    assert all(item.status == CheckStatus.OK for item in report.items)


def test_health_check_missing_config_file():
    report = run_health_check(env_file="does-not-exist.env")

    assert not report.ok
    assert len(report.items) == 1
    assert report.items[0].name == "config"
    assert "not found" in report.items[0].detail


def test_health_check_invalid_config(tmp_path):
    env_file = tmp_path / "bad.env"
    env_file.write_text("FIRM_AI_PROVIDER_NAME=bogus\n", encoding="utf-8")

    report = run_health_check(env_file=str(env_file))

    assert not report.ok
    assert report.items[0].name == "config"
    assert "Invalid configuration" in report.items[0].detail


def test_health_check_missing_local_directory(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("FIRM_AI_DATA_DIR", str(blocked))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "data" / "audit.db"))

    report = run_health_check()

    assert not report.ok
    data_dir_item = next(item for item in report.items if item.name == "data_dir")
    assert data_dir_item.status == CheckStatus.FAIL


def test_health_check_provider_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "data" / "audit.db"))
    monkeypatch.setenv("FIRM_AI_PROVIDER_NAME", "approved")

    report = run_health_check()

    assert not report.ok
    provider_item = next(item for item in report.items if item.name == "provider_config")
    assert provider_item.status == CheckStatus.FAIL
    assert "provider_api_key" in provider_item.detail
