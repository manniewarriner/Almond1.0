"""Deterministic financial calculations.

Financial arithmetic must never be delegated to a language model. These
are the only calculation primitives the rest of the app is allowed to use
for percentage return and absolute change.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

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


# -- UK pension calculators (Calculator bot) ---------------------------------
#
# 2024/25 rates, England/NI. Illustrative only, not financial advice --
# these functions exist purely so the Calculator bot never asks the local
# model to do arithmetic it can get subtly wrong.

PERSONAL_ALLOWANCE = Decimal("12570")
# (band width, rate %) pairs, applied in order to taxable income above the
# personal allowance. The last band's width is None (no upper limit).
UK_INCOME_TAX_BANDS: tuple[tuple[Decimal | None, Decimal], ...] = (
    (Decimal("37700"), Decimal("20")),  # basic rate
    (Decimal("87440"), Decimal("40")),  # higher rate (up to £125,140 total income)
    (None, Decimal("45")),  # additional rate
)

STANDARD_ANNUAL_ALLOWANCE = Decimal("60000")
TAPER_ADJUSTED_INCOME_THRESHOLD = Decimal("260000")
TAPER_THRESHOLD_INCOME_THRESHOLD = Decimal("200000")
MINIMUM_TAPERED_ANNUAL_ALLOWANCE = Decimal("10000")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cumulative_tax(income: Decimal, personal_allowance: Decimal) -> Decimal:
    taxable = max(Decimal("0"), income - personal_allowance)
    tax = Decimal("0")
    remaining = taxable
    for width, rate in UK_INCOME_TAX_BANDS:
        if remaining <= 0:
            break
        chunk = remaining if width is None else min(remaining, width)
        tax += chunk * rate / Decimal(100)
        remaining -= chunk
    return tax


def pension_withdrawal_tax(
    withdrawal: Decimal,
    other_taxable_income: Decimal = Decimal("0"),
    tax_free_pct: Decimal = Decimal("25"),
) -> dict[str, Decimal]:
    """Tax-free lump sum plus marginal UK income tax on the rest of a pension
    withdrawal, stacked on top of any other taxable income for the tax year."""
    if withdrawal < 0:
        raise CalculationError("withdrawal cannot be negative")
    if other_taxable_income < 0:
        raise CalculationError("other_taxable_income cannot be negative")
    tax_free = _round_money(withdrawal * tax_free_pct / Decimal(100))
    taxable_withdrawal = withdrawal - tax_free
    tax_before = _cumulative_tax(other_taxable_income, PERSONAL_ALLOWANCE)
    tax_after = _cumulative_tax(other_taxable_income + taxable_withdrawal, PERSONAL_ALLOWANCE)
    tax_due = _round_money(tax_after - tax_before)
    return {
        "tax_free_amount": tax_free,
        "taxable_amount": taxable_withdrawal,
        "tax_due": tax_due,
        "net_amount": _round_money(withdrawal - tax_due),
    }


def carry_forward(
    prior_years: tuple[tuple[Decimal, Decimal], ...],
    current_year_allowance: Decimal = STANDARD_ANNUAL_ALLOWANCE,
) -> dict[str, object]:
    """Unused UK pension annual allowance carried forward from up to the
    previous 3 tax years (each `(allowance, used)` pair, oldest first)."""
    if len(prior_years) > 3:
        raise CalculationError("carry forward only looks back 3 tax years")
    unused_by_year = []
    for allowance, used in prior_years:
        if allowance < 0 or used < 0:
            raise CalculationError("allowance and used amounts cannot be negative")
        unused_by_year.append(max(Decimal("0"), allowance - used))
    total_unused = sum(unused_by_year, Decimal("0"))
    return {
        "unused_by_year": tuple(unused_by_year),
        "total_carry_forward": total_unused,
        "total_available_this_year": total_unused + current_year_allowance,
    }


def annual_allowance_position(
    net_income: Decimal = Decimal("0"),
    salary_sacrifice: Decimal = Decimal("0"),
    relief_at_source_contributions: Decimal = Decimal("0"),
    net_pay_contributions: Decimal = Decimal("0"),
    employer_contributions: Decimal = Decimal("0"),
    db_pension_input: Decimal = Decimal("0"),
    taxable_lump_sum_death_benefit: Decimal = Decimal("0"),
) -> dict[str, object]:
    """This tax year's threshold income, adjusted income, and applicable
    (possibly tapered) UK annual allowance, per HMRC's PTM057100 steps:

    Threshold income = net income - relief-at-source contributions
        + salary sacrifice / flexible remuneration - taxable lump sum death
        benefit.
    Adjusted income = net income + net pay arrangement (or other relief)
        contributions + employer contributions + DB/cash balance pension
        input - taxable lump sum death benefit. (Salary sacrifice is not
        added again here -- it should already be reflected in the employer
        contributions figure, since a sacrificed amount becomes an
        employer contribution.)
    """
    for name, value in (
        ("net_income", net_income),
        ("salary_sacrifice", salary_sacrifice),
        ("relief_at_source_contributions", relief_at_source_contributions),
        ("net_pay_contributions", net_pay_contributions),
        ("employer_contributions", employer_contributions),
        ("db_pension_input", db_pension_input),
        ("taxable_lump_sum_death_benefit", taxable_lump_sum_death_benefit),
    ):
        if value < 0:
            raise CalculationError(f"{name} cannot be negative")

    threshold_income = max(
        Decimal("0"),
        net_income
        - relief_at_source_contributions
        + salary_sacrifice
        - taxable_lump_sum_death_benefit,
    )
    adjusted_income = max(
        Decimal("0"),
        net_income
        + net_pay_contributions
        + employer_contributions
        + db_pension_input
        - taxable_lump_sum_death_benefit,
    )

    allowance = STANDARD_ANNUAL_ALLOWANCE
    if (
        adjusted_income > TAPER_ADJUSTED_INCOME_THRESHOLD
        and threshold_income > TAPER_THRESHOLD_INCOME_THRESHOLD
    ):
        reduction = (adjusted_income - TAPER_ADJUSTED_INCOME_THRESHOLD) / Decimal(2)
        allowance = max(MINIMUM_TAPERED_ANNUAL_ALLOWANCE, STANDARD_ANNUAL_ALLOWANCE - reduction)

    return {
        "threshold_income": threshold_income,
        "adjusted_income": adjusted_income,
        "annual_allowance": allowance,
        "tapered": allowance < STANDARD_ANNUAL_ALLOWANCE,
    }
