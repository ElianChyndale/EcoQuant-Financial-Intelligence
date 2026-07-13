"""Explicit-date bond valuation under a frozen Actual/Actual ICMA convention."""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date


DAY_COUNT_CONVENTION = "Actual/Actual ICMA"
COMPOUNDING_CONVENTION = "nominal annual yield compounded at coupon frequency"
_SUPPORTED_FREQUENCIES = (1, 2, 4, 12)


@dataclass(frozen=True)
class BondTerms:
    """Authoritative explicit-date terms for a fixed-rate bullet bond."""

    face_value: float
    coupon_rate: float
    payment_frequency: int
    maturity_date: date
    settlement_date: date
    issue_date: date
    first_coupon_date: date | None = None
    penultimate_coupon_date: date | None = None


@dataclass(frozen=True)
class BondCashFlow:
    """One remaining coupon/principal payment and its valuation timing."""

    payment_date: date
    coupon_amount: float
    principal_amount: float
    discount_periods: float
    time_years: float
    present_value: float


@dataclass(frozen=True)
class BondPricingResult:
    """Settlement-aware price, risk measures, schedule, and convention state."""

    dirty_price: float
    clean_price: float
    accrued_interest: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    yield_to_maturity: float
    spread_bps: int
    previous_coupon_date: date
    next_coupon_date: date
    remaining_coupons: int
    day_count_fraction: float
    cash_flows: tuple[BondCashFlow, ...]
    day_count_convention: str = DAY_COUNT_CONVENTION
    compounding_convention: str = COMPOUNDING_CONVENTION

    @property
    def price(self) -> float:
        """Compatibility alias for the dirty price."""
        return self.dirty_price


@dataclass(frozen=True)
class _CouponPeriod:
    start: date
    end: date
    quasi_intervals: tuple[tuple[date, date], ...]


def _is_month_end(value: date) -> bool:
    return value.day == calendar.monthrange(value.year, value.month)[1]


def _add_months(value: date, months: int, *, preserve_month_end: bool) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    last_day = calendar.monthrange(year, month)[1]
    day = last_day if preserve_month_end else min(value.day, last_day)
    return date(year, month, day)


def _validate_terms_and_market(
    terms: BondTerms,
    yield_to_maturity: float,
    spread_bps: int,
) -> float:
    if not math.isfinite(terms.face_value) or terms.face_value <= 0:
        raise ValueError("face_value must be positive and finite")
    if not math.isfinite(terms.coupon_rate) or terms.coupon_rate < 0:
        raise ValueError("coupon_rate must be non-negative and finite")
    if terms.payment_frequency not in _SUPPORTED_FREQUENCIES:
        raise ValueError("payment_frequency must be 1, 2, 4, or 12")
    for name in ("issue_date", "settlement_date", "maturity_date"):
        if type(getattr(terms, name)) is not date:
            raise TypeError(f"{name} must be a date")
    if not terms.issue_date <= terms.settlement_date < terms.maturity_date:
        raise ValueError("dates must satisfy issue_date <= settlement_date < maturity_date")
    if terms.issue_date >= terms.maturity_date:
        raise ValueError("maturity_date must be after issue_date")
    if not math.isfinite(yield_to_maturity):
        raise ValueError("yield_to_maturity must be finite")
    if type(spread_bps) is not int:
        raise TypeError("spread_bps must be integer basis points")
    periodic_yield = (
        yield_to_maturity + spread_bps / 10_000.0
    ) / terms.payment_frequency
    discount_base = 1.0 + periodic_yield
    if not math.isfinite(discount_base) or discount_base <= 0.0:
        raise ValueError("discount base must be positive and finite")
    return discount_base


def _backward_grid(anchor: date, issue_date: date, months: int) -> list[date]:
    preserve_month_end = _is_month_end(anchor)
    grid = [anchor]
    current = anchor
    for _ in range(1_000):
        previous = _add_months(
            current,
            -months,
            preserve_month_end=preserve_month_end,
        )
        if previous < issue_date:
            break
        grid.append(previous)
        if previous == issue_date:
            break
        current = previous
    else:
        raise ValueError("coupon schedule exceeds supported length")
    return sorted(grid)


def _quasi_intervals_backward(
    start: date,
    end: date,
    months: int,
) -> tuple[tuple[date, date], ...]:
    preserve_month_end = _is_month_end(end)
    intervals: list[tuple[date, date]] = []
    current = end
    for _ in range(2):
        previous = _add_months(
            current,
            -months,
            preserve_month_end=preserve_month_end,
        )
        intervals.append((previous, current))
        if previous <= start:
            return tuple(reversed(intervals))
        current = previous
    raise ValueError("stub spans more than two nominal coupon periods")


def _quasi_intervals_forward(
    start: date,
    end: date,
    months: int,
) -> tuple[tuple[date, date], ...]:
    preserve_month_end = _is_month_end(start)
    intervals: list[tuple[date, date]] = []
    current = start
    for _ in range(2):
        following = _add_months(
            current,
            months,
            preserve_month_end=preserve_month_end,
        )
        intervals.append((current, following))
        if following >= end:
            return tuple(intervals)
        current = following
    raise ValueError("stub spans more than two nominal coupon periods")


def _build_periods(terms: BondTerms) -> tuple[_CouponPeriod, ...]:
    months = 12 // terms.payment_frequency
    first = terms.first_coupon_date
    penultimate = terms.penultimate_coupon_date

    if first is not None and not terms.issue_date < first < terms.maturity_date:
        raise ValueError("first_coupon_date must be between issue and maturity")
    if penultimate is not None and not terms.issue_date < penultimate < terms.maturity_date:
        raise ValueError("penultimate_coupon_date must be between issue and maturity")
    if first is not None and penultimate is not None and first > penultimate:
        raise ValueError("first_coupon_date must not follow penultimate_coupon_date")

    regular_anchor = penultimate or terms.maturity_date
    grid = _backward_grid(regular_anchor, terms.issue_date, months)

    if first is None:
        if terms.issue_date not in grid:
            raise ValueError(
                "first_coupon_date is required when issue_date is off the coupon grid"
            )
        regular_dates = [value for value in grid if value > terms.issue_date]
    else:
        if first not in grid:
            raise ValueError("first_coupon_date must lie on the regular coupon grid")
        regular_dates = [value for value in grid if value >= first]

    coupon_dates = regular_dates
    if penultimate is not None:
        if not coupon_dates or coupon_dates[-1] != penultimate:
            raise ValueError("penultimate_coupon_date is not on the regular coupon grid")
        coupon_dates = [*coupon_dates, terms.maturity_date]
    elif not coupon_dates or coupon_dates[-1] != terms.maturity_date:
        raise ValueError("maturity_date must be the final coupon date")

    if not coupon_dates or len(coupon_dates) != len(set(coupon_dates)):
        raise ValueError("coupon schedule must contain unique payment dates")
    if any(left >= right for left, right in zip(coupon_dates, coupon_dates[1:])):
        raise ValueError("coupon schedule must be strictly increasing")

    periods: list[_CouponPeriod] = []
    period_start = terms.issue_date
    for coupon_date in coupon_dates:
        is_final_stub = penultimate is not None and coupon_date == terms.maturity_date
        quasi_intervals = (
            _quasi_intervals_forward(period_start, coupon_date, months)
            if is_final_stub
            else _quasi_intervals_backward(period_start, coupon_date, months)
        )
        periods.append(_CouponPeriod(period_start, coupon_date, quasi_intervals))
        period_start = coupon_date

    return tuple(periods)


def _icma_year_fraction(
    period: _CouponPeriod,
    start: date,
    end: date,
    frequency: int,
) -> float:
    if not period.start <= start <= end <= period.end:
        raise ValueError("accrual interval must lie within its coupon period")
    fraction = 0.0
    for quasi_start, quasi_end in period.quasi_intervals:
        overlap_start = max(start, quasi_start)
        overlap_end = min(end, quasi_end)
        overlap_days = (overlap_end - overlap_start).days
        if overlap_days <= 0:
            continue
        quasi_days = (quasi_end - quasi_start).days
        if quasi_days <= 0:
            raise ValueError("quasi-coupon interval must have positive length")
        fraction += overlap_days / (frequency * quasi_days)
    if not math.isfinite(fraction) or fraction < 0.0:
        raise ValueError("ICMA year fraction must be finite and non-negative")
    return fraction


def price_bond(
    terms: BondTerms,
    yield_to_maturity: float,
    spread_bps: int = 0,
) -> BondPricingResult:
    """Reprice remaining fixed cash flows under the frozen ICMA convention."""
    discount_base = _validate_terms_and_market(terms, yield_to_maturity, spread_bps)
    periods = _build_periods(terms)
    remaining_periods = [period for period in periods if period.end > terms.settlement_date]
    if not remaining_periods:
        raise ValueError("no remaining cash flows after settlement")

    current_period = remaining_periods[0]
    previous_coupon_date = current_period.start
    next_coupon_date = current_period.end
    accrued_year_fraction = _icma_year_fraction(
        current_period,
        current_period.start,
        terms.settlement_date,
        terms.payment_frequency,
    )
    current_coupon_fraction = _icma_year_fraction(
        current_period,
        current_period.start,
        current_period.end,
        terms.payment_frequency,
    )
    accrued_interest = terms.face_value * terms.coupon_rate * accrued_year_fraction
    day_count_fraction = (
        accrued_year_fraction / current_coupon_fraction
        if current_coupon_fraction > 0.0
        else 0.0
    )

    cash_flows: list[BondCashFlow] = []
    discount_periods = 0.0
    dirty_price = 0.0
    macaulay_numerator = 0.0
    convexity_numerator = 0.0

    for index, period in enumerate(remaining_periods):
        timing_start = terms.settlement_date if index == 0 else period.start
        timing_fraction = _icma_year_fraction(
            period,
            timing_start,
            period.end,
            terms.payment_frequency,
        )
        discount_periods += terms.payment_frequency * timing_fraction
        time_years = discount_periods / terms.payment_frequency
        coupon_fraction = _icma_year_fraction(
            period,
            period.start,
            period.end,
            terms.payment_frequency,
        )
        coupon_amount = terms.face_value * terms.coupon_rate * coupon_fraction
        principal_amount = terms.face_value if period.end == terms.maturity_date else 0.0
        cash_flow_amount = coupon_amount + principal_amount
        present_value = cash_flow_amount / discount_base**discount_periods
        if not math.isfinite(present_value):
            raise ValueError("present value must be finite")
        dirty_price += present_value
        macaulay_numerator += time_years * present_value
        convexity_numerator += (
            time_years
            * (time_years + 1.0 / terms.payment_frequency)
            * present_value
        )
        cash_flows.append(
            BondCashFlow(
                payment_date=period.end,
                coupon_amount=coupon_amount,
                principal_amount=principal_amount,
                discount_periods=discount_periods,
                time_years=time_years,
                present_value=present_value,
            )
        )

    if not math.isfinite(dirty_price) or dirty_price <= 0.0:
        raise ValueError("dirty price must be positive and finite")
    clean_price = dirty_price - accrued_interest
    macaulay_duration = macaulay_numerator / dirty_price
    modified_duration = macaulay_duration / discount_base
    convexity = convexity_numerator / (dirty_price * discount_base**2)
    outputs = (
        clean_price,
        accrued_interest,
        macaulay_duration,
        modified_duration,
        convexity,
    )
    if any(not math.isfinite(value) for value in outputs):
        raise ValueError("valuation outputs must be finite")

    return BondPricingResult(
        dirty_price=dirty_price,
        clean_price=clean_price,
        accrued_interest=accrued_interest,
        macaulay_duration=macaulay_duration,
        modified_duration=modified_duration,
        convexity=convexity,
        yield_to_maturity=yield_to_maturity,
        spread_bps=spread_bps,
        previous_coupon_date=previous_coupon_date,
        next_coupon_date=next_coupon_date,
        remaining_coupons=len(cash_flows),
        day_count_fraction=day_count_fraction,
        cash_flows=tuple(cash_flows),
    )


def price_bond_with_spread_shock(
    terms: BondTerms,
    base_yield: float,
    base_spread_bps: int,
    shock_bps: int,
) -> BondPricingResult:
    """Reprice from cash flows after an integer-basis-point spread shock."""
    if type(base_spread_bps) is not int or type(shock_bps) is not int:
        raise TypeError("spread and shock must be integer basis points")
    return price_bond(terms, base_yield, base_spread_bps + shock_bps)


def compute_duration_convexity_numerically(
    terms: BondTerms,
    yield_to_maturity: float,
    spread_bps: int = 0,
    delta: float = 0.0001,
) -> tuple[float, float]:
    """Verify modified duration and convexity by central yield differences."""
    if not math.isfinite(delta) or delta <= 0.0:
        raise ValueError("delta must be positive and finite")
    price_0 = price_bond(terms, yield_to_maturity, spread_bps).dirty_price
    price_up = price_bond(terms, yield_to_maturity + delta, spread_bps).dirty_price
    price_down = price_bond(terms, yield_to_maturity - delta, spread_bps).dirty_price
    duration = -(price_up - price_down) / (2.0 * delta * price_0)
    convexity = (price_up - 2.0 * price_0 + price_down) / (delta**2 * price_0)
    if not math.isfinite(duration) or not math.isfinite(convexity):
        raise ValueError("finite-difference risk measures must be finite")
    return duration, convexity
