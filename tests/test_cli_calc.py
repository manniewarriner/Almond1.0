"""Tests for the `firm-ai calc` CLI subcommands."""

from __future__ import annotations

from typer.testing import CliRunner

from app.cli import app

runner = CliRunner()


def test_calc_percentage_return_success():
    result = runner.invoke(app, ["calc", "percentage-return", "--start", "100", "--end", "110"])

    assert result.exit_code == 0
    assert "10" in result.stdout


def test_calc_absolute_change_success():
    result = runner.invoke(app, ["calc", "absolute-change", "--start", "100", "--end", "90"])

    assert result.exit_code == 0
    assert "-10" in result.stdout


def test_calc_percentage_return_zero_start():
    result = runner.invoke(app, ["calc", "percentage-return", "--start", "0", "--end", "10"])

    assert result.exit_code == 1
    assert "Calculation error" in result.stdout


def test_calc_invalid_number():
    result = runner.invoke(app, ["calc", "absolute-change", "--start", "abc", "--end", "10"])

    assert result.exit_code == 1
    assert "Calculation error" in result.stdout
