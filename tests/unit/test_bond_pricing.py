"""Independent fixtures for the frozen Task 7A ICMA valuation contract."""

from __future__ import annotations

from datetime import date
import math

import pytest

from ecoquant.valuation.bond_pricing import (
    BondTerms,
    compute_duration_convexity_numerically,
    price_bond,
    price_bond_with_spread_shock,
)


def _terms(**overrides: object) -> BondTerms:
    values: dict[str, object] = {
        "face_value": 1_000.0,
        "coupon_rate": 0.06,
        "payment_frequency": 2,
        "issue_date": date(2024, 1, 31),
        "settlement_date": date(2025, 1, 31),
        "maturity_date": date(2027, 1, 31),
    }
    values.update(overrides)
    return BondTerms(**values)  # type: ignore[arg-type]


def _regular_price(face: float, coupon: float, periodic_yield: float, periods: int) -> float:
    return sum(
        (coupon + (face if period == periods else 0.0))
        / (1.0 + periodic_yield) ** period
        for period in range(1, periods + 1)
    )


def test_authoritative_terms_require_explicit_maturity_date() -> None:
    terms = _terms()
    assert terms.maturity_date == date(2027, 1, 31)
    assert not hasattr(terms, "maturity_years")


def test_fractional_maturity_years_are_not_silently_truncated() -> None:
    with pytest.raises(TypeError):
        BondTerms(
            face_value=1_000.0,
            coupon_rate=0.05,
            payment_frequency=2,
            issue_date=date(2024, 1, 31),
            settlement_date=date(2024, 1, 31),
            maturity_years=5.5,  # type: ignore[call-arg]
        )


def test_regular_par_bond_matches_hand_formula() -> None:
    result = price_bond(_terms(), yield_to_maturity=0.06)
    assert result.dirty_price == pytest.approx(1_000.0, abs=1e-10)
    assert result.clean_price == pytest.approx(1_000.0, abs=1e-10)
    assert result.accrued_interest == 0.0


@pytest.mark.parametrize(
    ("coupon_rate", "yield_rate", "comparison"),
    [(0.06, 0.04, "premium"), (0.04, 0.06, "discount")],
)
def test_premium_and_discount_bonds_match_hand_formulas(
    coupon_rate: float,
    yield_rate: float,
    comparison: str,
) -> None:
    terms = _terms(coupon_rate=coupon_rate)
    result = price_bond(terms, yield_to_maturity=yield_rate)
    expected = _regular_price(
        1_000.0,
        1_000.0 * coupon_rate / 2,
        yield_rate / 2,
        4,
    )
    assert result.dirty_price == pytest.approx(expected, rel=1e-12)
    assert (result.clean_price > 1_000.0) is (comparison == "premium")


def test_zero_coupon_bond_matches_hand_formula() -> None:
    terms = _terms(
        coupon_rate=0.0,
        payment_frequency=1,
        issue_date=date(2025, 1, 1),
        settlement_date=date(2025, 1, 1),
        maturity_date=date(2027, 1, 1),
    )
    result = price_bond(terms, yield_to_maturity=0.05)
    assert result.dirty_price == pytest.approx(1_000.0 / 1.05**2, rel=1e-12)
    assert result.macaulay_duration == pytest.approx(2.0)


def test_between_coupon_settlement_uses_icma_period_fraction() -> None:
    terms = _terms(settlement_date=date(2025, 4, 30))
    result = price_bond(terms, yield_to_maturity=0.06)
    elapsed = 89 / 181
    remaining = 92 / 181
    expected_accrued = 30.0 * elapsed
    expected_dirty = sum(
        cash_flow / 1.03 ** (remaining + offset)
        for offset, cash_flow in enumerate((30.0, 30.0, 30.0, 1_030.0))
    )
    assert result.previous_coupon_date == date(2025, 1, 31)
    assert result.next_coupon_date == date(2025, 7, 31)
    assert result.accrued_interest == pytest.approx(expected_accrued, rel=1e-12)
    assert result.dirty_price == pytest.approx(expected_dirty, rel=1e-12)
    assert result.dirty_price == pytest.approx(
        result.clean_price + result.accrued_interest,
        rel=1e-12,
    )


def test_settlement_on_coupon_date_has_zero_accrued_interest() -> None:
    result = price_bond(_terms(), yield_to_maturity=0.06)
    assert result.previous_coupon_date == date(2025, 1, 31)
    assert result.next_coupon_date == date(2025, 7, 31)
    assert result.accrued_interest == 0.0


def test_short_first_stub_coupon_is_prorated() -> None:
    terms = _terms(
        issue_date=date(2024, 4, 30),
        settlement_date=date(2024, 4, 30),
        first_coupon_date=date(2024, 7, 31),
        maturity_date=date(2025, 7, 31),
    )
    result = price_bond(terms, yield_to_maturity=0.0)
    expected_stub = 1_000.0 * 0.06 * (92 / (182 * 2))
    assert result.cash_flows[0].payment_date == date(2024, 7, 31)
    assert result.cash_flows[0].coupon_amount == pytest.approx(expected_stub, rel=1e-12)
    assert result.cash_flows[0].coupon_amount < 30.0


def test_long_first_stub_uses_two_icma_quasi_periods() -> None:
    terms = _terms(
        issue_date=date(2024, 1, 31),
        settlement_date=date(2024, 1, 31),
        first_coupon_date=date(2025, 1, 31),
        maturity_date=date(2026, 1, 31),
    )
    result = price_bond(terms, yield_to_maturity=0.0)
    assert result.cash_flows[0].payment_date == date(2025, 1, 31)
    assert result.cash_flows[0].coupon_amount == pytest.approx(60.0, abs=1e-12)


@pytest.mark.parametrize(
    ("penultimate", "maturity", "expected_coupon"),
    [
        (date(2025, 7, 31), date(2025, 10, 31), 30.0 * 92 / 184),
        (date(2025, 1, 31), date(2025, 10, 31), 30.0 + 30.0 * 92 / 184),
    ],
)
def test_final_stub_uses_forward_icma_quasi_periods(
    penultimate: date,
    maturity: date,
    expected_coupon: float,
) -> None:
    terms = _terms(
        issue_date=date(2024, 1, 31),
        settlement_date=date(2024, 1, 31),
        penultimate_coupon_date=penultimate,
        maturity_date=maturity,
    )
    result = price_bond(terms, yield_to_maturity=0.0)
    assert result.cash_flows[-1].coupon_amount == pytest.approx(expected_coupon, rel=1e-12)


def test_end_of_month_and_leap_year_schedule_remains_valid() -> None:
    terms = _terms(
        issue_date=date(2023, 8, 31),
        settlement_date=date(2023, 8, 31),
        maturity_date=date(2025, 8, 31),
    )
    result = price_bond(terms, yield_to_maturity=0.06)
    assert tuple(flow.payment_date for flow in result.cash_flows) == (
        date(2024, 2, 29),
        date(2024, 8, 31),
        date(2025, 2, 28),
        date(2025, 8, 31),
    )


def test_maturity_principal_is_paid_exactly_once() -> None:
    result = price_bond(_terms(), yield_to_maturity=0.06)
    principal_flows = [flow for flow in result.cash_flows if flow.principal_amount]
    assert len(principal_flows) == 1
    assert principal_flows[0].payment_date == date(2027, 1, 31)
    assert principal_flows[0].principal_amount == 1_000.0


def test_ambiguous_implicit_stub_schedule_is_rejected() -> None:
    terms = _terms(
        issue_date=date(2024, 4, 30),
        settlement_date=date(2024, 4, 30),
        maturity_date=date(2025, 7, 31),
    )
    with pytest.raises(ValueError, match="first_coupon_date"):
        price_bond(terms, yield_to_maturity=0.05)


def test_stub_longer_than_two_nominal_periods_is_rejected() -> None:
    terms = _terms(
        issue_date=date(2024, 1, 31),
        settlement_date=date(2024, 1, 31),
        first_coupon_date=date(2025, 7, 31),
        maturity_date=date(2026, 7, 31),
    )
    with pytest.raises(ValueError, match="more than two"):
        price_bond(terms, yield_to_maturity=0.05)


@pytest.mark.parametrize(
    ("overrides", "yield_rate", "spread", "error"),
    [
        ({"coupon_rate": float("nan")}, 0.05, 0, "coupon_rate"),
        ({"face_value": 0.0}, 0.05, 0, "face_value"),
        ({"payment_frequency": 3}, 0.05, 0, "payment_frequency"),
        ({"settlement_date": date(2027, 1, 31)}, 0.05, 0, "dates"),
        ({}, float("nan"), 0, "yield"),
        ({}, -2.0, 0, "discount base"),
    ],
)
def test_invalid_pricing_inputs_fail_explicitly(
    overrides: dict[str, object],
    yield_rate: float,
    spread: int,
    error: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        price_bond(_terms(**overrides), yield_rate, spread)


def test_noninteger_basis_points_and_unstable_finite_difference_are_rejected() -> None:
    terms = _terms()
    with pytest.raises(TypeError, match="basis points"):
        price_bond(terms, 0.05, 1.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="delta"):
        compute_duration_convexity_numerically(terms, 0.05, delta=0.0)


def test_increasing_yield_and_100bp_spread_shock_lower_price() -> None:
    terms = _terms()
    lower = price_bond(terms, yield_to_maturity=0.05)
    higher = price_bond(terms, yield_to_maturity=0.06)
    shocked = price_bond_with_spread_shock(terms, 0.05, 0, 100)
    assert higher.dirty_price < lower.dirty_price
    assert shocked.dirty_price == pytest.approx(higher.dirty_price, rel=1e-12)


@pytest.mark.parametrize(
    "case",
    ["coupon_date", "between_coupon", "short_stub"],
)
def test_duration_and_convexity_match_one_bp_finite_differences(case: str) -> None:
    if case == "coupon_date":
        terms = _terms()
    elif case == "between_coupon":
        terms = _terms(settlement_date=date(2025, 4, 30))
    else:
        terms = _terms(
            issue_date=date(2024, 4, 30),
            settlement_date=date(2024, 4, 30),
            first_coupon_date=date(2024, 7, 31),
            maturity_date=date(2025, 7, 31),
        )
    result = price_bond(terms, yield_to_maturity=0.05)
    numerical_duration, numerical_convexity = compute_duration_convexity_numerically(
        terms,
        yield_to_maturity=0.05,
        delta=0.0001,
    )
    assert result.modified_duration == pytest.approx(numerical_duration, rel=2e-7)
    assert result.convexity == pytest.approx(numerical_convexity, rel=2e-6)
    assert all(
        math.isfinite(value)
        for value in (
            result.macaulay_duration,
            result.modified_duration,
            result.convexity,
        )
    )


def test_duration_and_convexity_improve_price_approximation() -> None:
    terms = _terms(settlement_date=date(2025, 4, 30))
    base = price_bond(terms, yield_to_maturity=0.05)
    shifted = price_bond(terms, yield_to_maturity=0.0501)
    dy = 0.0001
    first_order = base.dirty_price * (1.0 - base.modified_duration * dy)
    second_order = base.dirty_price * (
        1.0 - base.modified_duration * dy + 0.5 * base.convexity * dy**2
    )
    assert abs(shifted.dirty_price - second_order) < abs(
        shifted.dirty_price - first_order
    )
