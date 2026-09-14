"""Deterministic financial calculations.

Financial arithmetic must never be delegated to a language model. These
are the only calculation primitives the rest of the app is allowed to use
for percentage return and absolute change.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.errors import CalculationError


def to_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise CalculationError(f"Not a valid number: {value!r}") from exc


def absolute_change(start: Decimal, end: Decimal) -> Decimal:
    return end - start


def percentage_return(start: Decimal, end: Decimal) -> Decimal:
    if start == 0:
        raise CalculationError("start value cannot be zero for percentage return")
    return (end - start) / start * Decimal(100)
