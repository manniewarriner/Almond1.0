"""Tests for the bundled local llama.cpp server lifecycle and path safety."""

from __future__ import annotations

import inspect

import pytest

from app.errors import ProviderError
from app.local_model import LocalModelServer, resolve_model_path


def test_resolve_model_path_accepts_plain_filename(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    resolved = resolve_model_path("model.gguf", models_dir)

    assert resolved == (models_dir / "model.gguf").resolve()


@pytest.mark.parametrize(
    "model_file",
    [
        "../model.gguf",
        "../../etc/passwd",
        "sub/../../escape.gguf",
    ],
)
def test_resolve_model_path_rejects_traversal(tmp_path, model_file):
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    with pytest.raises(ProviderError):
        resolve_model_path(model_file, models_dir)


def test_resolve_model_path_rejects_absolute_path(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    absolute = str(tmp_path / "outside.gguf")

    with pytest.raises(ProviderError):
        resolve_model_path(absolute, models_dir)


def test_local_model_server_rejects_traversal_at_construction(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    server_exe = tmp_path / "llama-server.exe"
    server_exe.write_text("stub", encoding="utf-8")

    with pytest.raises(ProviderError):
        LocalModelServer("../secrets.gguf", server_exe=server_exe, models_dir=models_dir)


def test_local_model_server_start_fails_cleanly_when_runtime_missing(tmp_path, monkeypatch):
    # is_ready() probes real port 11435; force it False so this test's
    # missing-file assertion never depends on what else is using that port.
    monkeypatch.setattr(LocalModelServer, "is_ready", staticmethod(lambda: False))
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "model.gguf").write_text("stub", encoding="utf-8")
    missing_exe = tmp_path / "does-not-exist.exe"

    server = LocalModelServer("model.gguf", server_exe=missing_exe, models_dir=models_dir)

    with pytest.raises(ProviderError, match="runtime is missing"):
        server.start()


def test_local_model_server_start_fails_cleanly_when_model_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(LocalModelServer, "is_ready", staticmethod(lambda: False))
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    server_exe = tmp_path / "llama-server.exe"
    server_exe.write_text("stub", encoding="utf-8")

    server = LocalModelServer("missing.gguf", server_exe=server_exe, models_dir=models_dir)

    with pytest.raises(ProviderError, match="model file is missing"):
        server.start()


def test_local_model_source_binds_loopback_only():
    import app.local_model as local_model_module

    source = inspect.getsource(local_model_module)

    assert 'LOOPBACK_HOST = "127.0.0.1"' in source
    assert "--host" in source
    assert "0.0.0.0" not in source
