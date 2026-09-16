"""Tests for the `almond pdf create` CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from app.cli import app

runner = CliRunner()


def test_pdf_create_succeeds_for_authorized_user(tmp_path, monkeypatch):
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.\n\nSecond paragraph.", encoding="utf-8")
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("FIRM_AI_OUTPUTS_DIR", str(outputs))

    result = runner.invoke(app, ["pdf", "create", str(source)])

    assert result.exit_code == 0
    assert "PDF generated" in result.stdout
    assert "Output verified" in result.stdout
    assert (outputs / "notes-almond.pdf").is_file()


def test_pdf_create_unknown_user_denied(tmp_path, monkeypatch):
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.", encoding="utf-8")
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("FIRM_AI_OUTPUTS_DIR", str(outputs))

    result = runner.invoke(app, ["pdf", "create", str(source), "--user", "mallory"])

    assert result.exit_code == 1
    assert "Missing permission" in result.stdout
    assert not outputs.exists()


def test_pdf_create_unsupported_type_shows_clean_error(tmp_path, monkeypatch):
    source = tmp_path / "sheet.xlsx"
    source.write_bytes(b"not real")
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("FIRM_AI_OUTPUTS_DIR", str(outputs))

    result = runner.invoke(app, ["pdf", "create", str(source)])

    assert result.exit_code == 1
    assert "PDF generation failed" in result.stdout
    assert "Unsupported document type: .xlsx" in result.stdout
    assert "Traceback" not in result.stdout


def test_pdf_create_missing_source_shows_clean_error(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("FIRM_AI_OUTPUTS_DIR", str(outputs))

    result = runner.invoke(app, ["pdf", "create", str(tmp_path / "missing.txt")])

    assert result.exit_code == 1
    assert "PDF generation failed" in result.stdout
    assert "not found" in result.stdout


def test_pdf_create_title_override(tmp_path, monkeypatch):
    source = tmp_path / "notes.txt"
    source.write_text("Body text.", encoding="utf-8")
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("FIRM_AI_OUTPUTS_DIR", str(outputs))

    result = runner.invoke(app, ["pdf", "create", str(source), "--title", "Custom Title"])

    assert result.exit_code == 0
    assert (outputs / "notes-almond.pdf").is_file()
