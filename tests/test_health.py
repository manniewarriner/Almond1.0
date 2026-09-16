"""Tests for app.health: config, directories, audit db, provider syntax checks."""

from __future__ import annotations

import app.health as health
from app.health import run_health_check
from app.models import CheckStatus


def _use_fake_local_runtime(tmp_path, monkeypatch):
    server_exe = tmp_path / "runtime" / "llama.cpp" / "llama-server.exe"
    models_dir = tmp_path / "runtime" / "models"
    server_exe.parent.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    server_exe.write_text("stub", encoding="utf-8")
    (models_dir / "MiniCPM5-2B-Q4_K_M.gguf").write_text("stub", encoding="utf-8")
    monkeypatch.setattr(health, "DEFAULT_SERVER_EXE", server_exe)
    monkeypatch.setattr(health, "DEFAULT_MODELS_DIR", models_dir)


def test_health_check_success(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "data" / "audit.db"))
    _use_fake_local_runtime(tmp_path, monkeypatch)

    report = run_health_check()

    assert report.ok
    names = {item.name for item in report.items}
    assert names == {
        "config",
        "data_dir",
        "audit_db",
        "provider_config",
        "local_runtime",
        "model_file",
        "model_status",
    }
    assert all(item.status == CheckStatus.OK for item in report.items)


def test_health_check_reports_missing_local_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "data" / "audit.db"))
    monkeypatch.setattr(health, "DEFAULT_SERVER_EXE", tmp_path / "missing-server.exe")
    monkeypatch.setattr(health, "DEFAULT_MODELS_DIR", tmp_path / "runtime" / "models")

    report = run_health_check()

    assert not report.ok
    runtime_item = next(item for item in report.items if item.name == "local_runtime")
    assert runtime_item.status == CheckStatus.FAIL
    status_item = next(item for item in report.items if item.name == "model_status")
    assert status_item.status == CheckStatus.FAIL


def test_health_check_reports_missing_model_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRM_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIRM_AI_AUDIT_DB_PATH", str(tmp_path / "data" / "audit.db"))
    server_exe = tmp_path / "runtime" / "llama.cpp" / "llama-server.exe"
    server_exe.parent.mkdir(parents=True)
    server_exe.write_text("stub", encoding="utf-8")
    monkeypatch.setattr(health, "DEFAULT_SERVER_EXE", server_exe)
    monkeypatch.setattr(health, "DEFAULT_MODELS_DIR", tmp_path / "runtime" / "models")

    report = run_health_check()

    assert not report.ok
    model_item = next(item for item in report.items if item.name == "model_file")
    assert model_item.status == CheckStatus.FAIL
    assert "Missing model file" in model_item.detail


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
