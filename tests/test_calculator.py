"""Tests for app.tools.calculator: pure deterministic financial arithmetic."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.errors import CalculationError
from app.tools.calculator import absolute_change, percentage_return, to_decimal


def test_to_decimal_valid():
    assert to_decimal("100.5") == Decimal("100.5")


def test_to_decimal_invalid():
    with pytest.raises(CalculationError):
        to_decimal("not-a-number")


def test_absolute_change_positive():
    assert absolute_change(Decimal("100"), Decimal("110")) == Decimal("10")


def test_absolute_change_negative():
    assert absolute_change(Decimal("100"), Decimal("90")) == Decimal("-10")


def test_percentage_return_positive():
    assert percentage_return(Decimal("100"), Decimal("110")) == Decimal("10")


def test_percentage_return_negative():
    assert percentage_return(Decimal("100"), Decimal("90")) == Decimal("-10")


def test_percentage_return_zero_start_raises():
    with pytest.raises(CalculationError):
        percentage_return(Decimal("0"), Decimal("10"))
