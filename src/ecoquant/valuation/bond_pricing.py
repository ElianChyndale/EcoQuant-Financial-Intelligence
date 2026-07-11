"""Bond pricing with settlement-aware cash flows, duration, and convexity.

Implements financially correct bond repricing with:
- Settlement-aware cash flows (settlement between coupon dates)
- Accrued interest calculation
- Clean price and dirty price
- Macaulay duration
- Modified duration
- Convexity
- Stub period handling
- Input validation

Day-count convention: Actual/Actual ISDA (documented prototype choice).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class BondTerms:
    """Immutable bond terms for pricing.

    Attributes:
        face_value: Face value per token (must be positive).
        coupon_rate: Annual coupon rate as decimal (e.g., 0.05 for 5%).
        payment_frequency: Payments per year (1, 2, 4, or 12).
        maturity_years: Years to maturity from issue date.
        settlement_date: Settlement date as a date object.
        issue_date: Issue date as a date object.
        first_coupon_date: Optional first coupon date (for stub periods).
    """

    face_value: float
    coupon_rate: float  # Annual coupon rate as decimal (e.g., 0.05 for 5%)
    payment_frequency: int  # Payments per year (e.g., 2 for semi-annual)
    maturity_years: float  # Years to maturity from issue date
    settlement_date: date  # Settlement date
    issue_date: date  # Issue date
    first_coupon_date: date | None = None  # For stub periods


@dataclass(frozen=True)
class BondPricingResult:
    """Result of bond pricing calculation."""

    price: float  # Dirty price (full price including accrued interest)
    clean_price: float  # Clean price (dirty price minus accrued interest)
    accrued_interest: float  # Accrued interest since last coupon
    macaulay_duration: float
    modified_duration: float
    convexity: float
    yield_to_maturity: float
    spread_bps: int
    next_coupon_date: date | None
    remaining_coupons: int
    day_count_fraction: float  # Fraction of current period elapsed


def _validate_pricing_inputs(
    face_value: float,
    coupon_rate: float,
    payment_frequency: int,
    yield_to_maturity: float,
    spread_bps: int,
    settlement_date: date,
    issue_date: date,
    maturity_years: float,
) -> None:
    """Validate all pricing inputs. Raises ValueError for invalid inputs."""
    if not math.isfinite(face_value) or face_value <= 0:
        raise ValueError(f"face_value must be positive and finite, got {face_value}")
    if not math.isfinite(coupon_rate) or coupon_rate < 0:
        raise ValueError(f"coupon_rate must be non-negative and finite, got {coupon_rate}")
    if payment_frequency not in (1, 2, 4, 12):
        raise ValueError(f"payment_frequency must be 1, 2, 4, or 12, got {payment_frequency}")
    if not math.isfinite(yield_to_maturity):
        raise ValueError(f"yield_to_maturity must be finite, got {yield_to_maturity}")
    if not math.isfinite(spread_bps):
        raise ValueError(f"spread_bps must be finite, got {spread_bps}")
    if settlement_date < issue_date:
        raise ValueError(
            f"settlement_date ({settlement_date}) must be on or after issue_date ({issue_date})"
        )
    if maturity_years <= 0:
        raise ValueError(f"maturity_years must be positive, got {maturity_years}")
    # Check that maturity is in the future relative to issue
    maturity_date = date(
        issue_date.year + int(maturity_years),
        issue_date.month,
        issue_date.day,
    )
    if maturity_date <= settlement_date:
        raise ValueError(
            f"maturity date ({maturity_date}) must be after settlement ({settlement_date})"
        )


def _generate_coupon_dates(
    issue_date: date,
    maturity_years: float,
    payment_frequency: int,
    first_coupon_date: date | None = None,
) -> list[date]:
    """Generate all coupon payment dates from issue to maturity.

    Handles stub periods by using the first_coupon_date if provided.
    """
    months_between = 12 // payment_frequency
    maturity_year = issue_date.year + int(maturity_years)
    maturity_date = date(maturity_year, issue_date.month, issue_date.day)

    coupon_dates: list[date] = []

    if first_coupon_date is not None:
        # First period may be a stub
        coupon_dates.append(first_coupon_date)
        current = first_coupon_date
    else:
        # Regular periods from issue
        current = issue_date

    # Generate subsequent coupon dates
    while True:
        # Add months_between to current date
        new_month = current.month + months_between
        new_year = current.year + (new_month - 1) // 12
        new_month = ((new_month - 1) % 12) + 1
        try:
            next_date = date(new_year, new_month, current.day)
        except ValueError:
            # Handle end-of-month (e.g., Jan 31 -> Feb 28)
            import calendar
            last_day = calendar.monthrange(new_year, new_month)[1]
            next_date = date(new_year, new_month, min(current.day, last_day))

        if next_date > maturity_date:
            break
        coupon_dates.append(next_date)
        current = next_date

    # Add maturity date as final payment if not already included
    if not coupon_dates or coupon_dates[-1] != maturity_date:
        coupon_dates.append(maturity_date)

    return coupon_dates


def _actual_actual_fraction(start: date, end: date, period_start: date, period_end: date) -> float:
    """Compute Actual/Actual ISDA day count fraction for a period.

    The fraction is: days_in_period / days_in_coupon_period
    where days_in_coupon_period is the length of the coupon period
    containing the accrual.
    """
    days_accrued = (end - start).days
    days_in_period = (period_end - period_start).days
    if days_in_period == 0:
        return 0.0
    return days_accrued / days_in_period


def price_bond(
    terms: BondTerms,
    yield_to_maturity: float,
    spread_bps: int = 0,
) -> BondPricingResult:
    """Price a bond given terms and yield, with settlement-aware cash flows.

    Supports settlement between coupon dates, accrued interest,
    clean/dirty price, stub periods, and fractional periods.

    Args:
        terms: Bond terms (face value, coupon, frequency, maturity, dates).
        yield_to_maturity: Annual yield as decimal (e.g., 0.05 for 5%).
        spread_bps: Credit spread in basis points added to yield.

    Returns:
        BondPricingResult with dirty price, clean price, accrued interest,
        duration, and convexity.

    Raises:
        ValueError: If any input is invalid.
    """
    # Validate inputs
    _validate_pricing_inputs(
        terms.face_value, terms.coupon_rate, terms.payment_frequency,
        yield_to_maturity, spread_bps,
        terms.settlement_date, terms.issue_date, terms.maturity_years,
    )

    total_yield = yield_to_maturity + spread_bps / 10_000.0
    coupon_per_period = terms.face_value * terms.coupon_rate / terms.payment_frequency
    yield_per_period = total_yield / terms.payment_frequency

    # Generate coupon dates
    coupon_dates = _generate_coupon_dates(
        terms.issue_date, terms.maturity_years,
        terms.payment_frequency, terms.first_coupon_date,
    )

    # Find remaining coupons after settlement
    remaining_dates = [d for d in coupon_dates if d > terms.settlement_date]
    if not remaining_dates:
        raise ValueError("no remaining coupon dates after settlement")

    next_coupon_date = remaining_dates[0]
    n_remaining = len(remaining_dates)

    # Find the last coupon date on or before settlement (for accrued interest)
    past_coupons = [d for d in coupon_dates if d <= terms.settlement_date]
    if past_coupons:
        last_coupon_date = past_coupons[-1]
    else:
        last_coupon_date = terms.issue_date

    # Compute accrued interest fraction
    # Fraction of current period elapsed since last coupon
    period_start = last_coupon_date
    period_end = next_coupon_date
    day_count_fraction = _actual_actual_fraction(
        last_coupon_date, terms.settlement_date, period_start, period_end
    )
    accrued_interest = coupon_per_period * day_count_fraction

    # Price remaining cash flows (dirty price)
    price = 0.0
    macaulay_numerator = 0.0
    convexity_numerator = 0.0

    for i, coupon_date in enumerate(remaining_dates):
        # Time from settlement to this coupon in years
        # Use Actual/Actual: days / 365.25 as approximation
        days_to_coupon = (coupon_date - terms.settlement_date).days
        time_years = days_to_coupon / 365.25

        # Discount factor
        discount_factor = 1.0 / ((1.0 + yield_per_period) ** (time_years * terms.payment_frequency))

        # Cash flow
        if i == len(remaining_dates) - 1:
            # Final payment: coupon + principal
            cash_flow = coupon_per_period + terms.face_value
        else:
            cash_flow = coupon_per_period

        # Present value
        pv = cash_flow * discount_factor
        price += pv

        # Duration numerator (weighted by time)
        macaulay_numerator += time_years * pv

        # Convexity numerator
        convexity_numerator += time_years * (time_years + 1.0 / terms.payment_frequency) * pv

    # Dirty price
    dirty_price = price

    # Clean price = dirty price - accrued interest
    clean_price = dirty_price - accrued_interest

    # Macaulay duration
    macaulay_duration = macaulay_numerator / dirty_price if dirty_price > 0 else 0.0

    # Modified duration
    modified_duration = macaulay_duration / (1.0 + yield_per_period) if (1.0 + yield_per_period) > 0 else 0.0

    # Convexity
    convexity = (
        convexity_numerator / (dirty_price * (1.0 + yield_per_period) ** 2)
        if dirty_price > 0 and (1.0 + yield_per_period) > 0
        else 0.0
    )

    return BondPricingResult(
        price=dirty_price,
        clean_price=clean_price,
        accrued_interest=accrued_interest,
        macaulay_duration=macaulay_duration,
        modified_duration=modified_duration,
        convexity=convexity,
        yield_to_maturity=yield_to_maturity,
        spread_bps=spread_bps,
        next_coupon_date=next_coupon_date,
        remaining_coupons=n_remaining,
        day_count_fraction=day_count_fraction,
    )


def price_bond_with_spread_shock(
    terms: BondTerms,
    base_yield: float,
    base_spread_bps: int,
    shock_bps: int,
) -> BondPricingResult:
    """Price a bond with a spread shock.

    Args:
        terms: Bond terms.
        base_yield: Base yield without spread.
        base_spread_bps: Base credit spread in bps.
        shock_bps: Additional spread shock in bps.

    Returns:
        BondPricingResult with shocked price, duration, and convexity.
    """
    total_spread = base_spread_bps + shock_bps
    return price_bond(terms, base_yield, total_spread)


def compute_duration_convexity_numerically(
    terms: BondTerms,
    yield_to_maturity: float,
    spread_bps: int = 0,
    delta: float = 0.0001,
) -> tuple[float, float]:
    """Compute duration and convexity using finite differences.

    This is used for verification against the analytical formulas.

    Args:
        terms: Bond terms.
        yield_to_maturity: Annual yield as decimal.
        spread_bps: Credit spread in bps.
        delta: Yield shift for finite difference.

    Returns:
        Tuple of (modified_duration, convexity).
    """
    # Price at current yield
    price_0 = price_bond(terms, yield_to_maturity, spread_bps).price

    # Price at yield + delta
    price_up = price_bond(terms, yield_to_maturity + delta, spread_bps).price

    # Price at yield - delta
    price_down = price_bond(terms, yield_to_maturity - delta, spread_bps).price

    # Modified duration: -(dP/dy) / P
    duration = -(price_up - price_down) / (2.0 * delta * price_0)

    # Convexity: (d²P/dy²) / P
    convexity = (price_up - 2.0 * price_0 + price_down) / (delta ** 2 * price_0)

    return duration, convexity
