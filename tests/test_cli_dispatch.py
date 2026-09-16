"""Tests for the `almond` entry point's dispatch between the TUI and
maintenance commands (almond_ai.cli.main)."""

from __future__ import annotations

from almond_ai.cli import LEGACY_COMMANDS, main


def test_pdf_is_a_recognized_maintenance_command():
    assert "pdf" in LEGACY_COMMANDS


def test_pdf_create_dispatches_to_maintenance_cli(monkeypatch):
    called = []
    monkeypatch.setattr("app.cli.main", lambda: called.append(True))
    monkeypatch.setattr("sys.argv", ["almond", "pdf", "create", "notes.txt"])

    main()

    assert called == [True]


def test_no_arguments_launches_almondcode(monkeypatch):
    called = []
    monkeypatch.setattr("almond_ai.code_cli.run", lambda: called.append(True))
    monkeypatch.setattr(
        "almond_ai.platform.apply_windows_console_branding",
        lambda app: called.append(("branding", app)),
    )
    monkeypatch.setattr("sys.argv", ["almond"])

    main()

    assert called == [("branding", "code"), True]


def test_dashboard_argument_launches_the_full_screen_tui(monkeypatch):
    called = []
    monkeypatch.setattr("almond_ai.app.run", lambda: called.append(True))
    monkeypatch.setattr(
        "almond_ai.platform.apply_windows_console_branding",
        lambda app: called.append(("branding", app)),
    )
    monkeypatch.setattr("sys.argv", ["almond", "dashboard"])

    main()

    assert called == [("branding", "dashboard"), True]
