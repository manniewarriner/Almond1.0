"""Tests for the /pdf slash command in the Textual developer console."""

from __future__ import annotations

from pathlib import Path

from almond_ai.app import AlmondDeveloperApp
from almond_ai.commands import parse_command
from almond_ai.config import DeveloperConfig


def test_pdf_help_lists_usage():
    app = AlmondDeveloperApp(DeveloperConfig())
    output = app._command_output("pdf", ("help",))
    assert "Almond PDF" in output
    assert "/pdf create" in output


def test_pdf_status_shows_output_directory():
    app = AlmondDeveloperApp(DeveloperConfig())
    output = app._command_output("pdf", ("status",))
    assert "Output directory" in output
    assert "Supported" in output


def test_pdf_create_generates_verified_pdf(tmp_path, monkeypatch):
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.\n\nSecond paragraph.", encoding="utf-8")
    outputs = tmp_path / "outputs"

    app = AlmondDeveloperApp(DeveloperConfig())
    app.base_config.outputs_dir = outputs
    app.permissions.add("documents:read")

    output = app._command_output("pdf", ("create", str(source)))

    assert "Document loaded" in output
    assert "words extracted" in output
    assert "PDF generated" in output
    assert "Output verified" in output
    assert (outputs / "notes-almond.pdf").is_file()
    assert app.tools.get("document_to_pdf").last_status == "success"


def test_pdf_create_without_permission_is_denied(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("Hello world.", encoding="utf-8")

    app = AlmondDeveloperApp(DeveloperConfig())
    app.base_config.outputs_dir = tmp_path / "outputs"
    app.permissions.discard("documents:read")

    try:
        app._command_output("pdf", ("create", str(source)))
        raised = False
    except PermissionError as exc:
        raised = "documents:read" in str(exc)
    assert raised
    assert not (tmp_path / "outputs").exists()


def test_pdf_create_unsupported_type_shows_friendly_error(tmp_path):
    source = tmp_path / "sheet.xlsx"
    source.write_bytes(b"not real")

    app = AlmondDeveloperApp(DeveloperConfig())
    app.base_config.outputs_dir = tmp_path / "outputs"
    app.permissions.add("documents:read")

    output = app._command_output("pdf", ("create", str(source)))

    assert "PDF generation failed" in output
    assert "Unsupported document type: .xlsx" in output


def test_pdf_create_missing_filename_raises_usage_error():
    app = AlmondDeveloperApp(DeveloperConfig())
    app.permissions.add("documents:read")

    try:
        app._command_output("pdf", ("create",))
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_pdf_create_with_quoted_filename_parses_correctly(tmp_path):
    source = tmp_path / "client notes.txt"
    source.write_text("Hello world.", encoding="utf-8")

    parsed = parse_command(f'/pdf create "{source}"')

    assert parsed is not None
    assert parsed.name == "pdf"
    assert parsed.args == ("create", str(source))


def test_pdf_create_with_title_override(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("Body text.", encoding="utf-8")
    outputs = tmp_path / "outputs"

    app = AlmondDeveloperApp(DeveloperConfig())
    app.base_config.outputs_dir = outputs
    app.permissions.add("documents:read")

    app._command_output("pdf", ("create", str(source), "--title", "Custom Title"))

    assert (outputs / "notes-almond.pdf").is_file()


def test_pdf_output_path_reported_and_no_traceback_leaks(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("Body text.", encoding="utf-8")
    outputs = tmp_path / "outputs"

    app = AlmondDeveloperApp(DeveloperConfig())
    app.base_config.outputs_dir = outputs
    app.permissions.add("documents:read")

    output = app._command_output("pdf", ("create", str(source)))

    assert (
        str((outputs / "notes-almond.pdf").resolve()) in output
        or str(Path(outputs / "notes-almond.pdf")) in output
    )
    assert "Traceback" not in output
