"""Bond pricing with duration and convexity calculations.

Implements financially correct bond repricing with:
- Present value of cash flows
- Macaulay duration
- Modified duration
- Convexity

All calculations use proper time fractions and yield conventions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BondTerms:
    """Immutable bond terms for pricing."""

    face_value: float
    coupon_rate: float  # Annual coupon rate as decimal (e.g., 0.05 for 5%)
    payment_frequency: int  # Payments per year (e.g., 2 for semi-annual)
    maturity_years: float  # Years to maturity
    settlement_date: float  # Fractional year from issue to settlement


@dataclass(frozen=True)
class BondPricingResult:
    """Result of bond pricing calculation."""

    price: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    yield_to_maturity: float
    spread_bps: int


def price_bond(
    terms: BondTerms,
    yield_to_maturity: float,
    spread_bps: int = 0,
) -> BondPricingResult:
    """Price a bond given terms and yield.

    Args:
        terms: Bond terms (face value, coupon, frequency, maturity).
        yield_to_maturity: Annual yield as decimal (e.g., 0.05 for 5%).
        spread_bps: Credit spread in basis points added to yield.

    Returns:
        BondPricingResult with price, duration, and convexity.
    """
    # Total yield including spread
    total_yield = yield_to_maturity + spread_bps / 10_000.0

    # Coupon payment per period
    coupon_per_period = terms.face_value * terms.coupon_rate / terms.payment_frequency

    # Number of periods
    n_periods = int(terms.maturity_years * terms.payment_frequency)

    # Yield per period
    yield_per_period = total_yield / terms.payment_frequency

    # Calculate present value of cash flows
    price = 0.0
    macaulay_numerator = 0.0
    convexity_numerator = 0.0

    for t in range(1, n_periods + 1):
        # Time in years
        time_years = t / terms.payment_frequency

        # Discount factor
        discount_factor = 1.0 / ((1.0 + yield_per_period) ** t)

        # Cash flow for this period
        if t == n_periods:
            cash_flow = coupon_per_period + terms.face_value  # Final payment includes principal
        else:
            cash_flow = coupon_per_period

        # Present value of this cash flow
        pv = cash_flow * discount_factor
        price += pv

        # Macaulay duration numerator (weighted by time)
        macaulay_numerator += time_years * pv

        # Convexity numerator
        convexity_numerator += time_years * (time_years + 1.0 / terms.payment_frequency) * pv

    # Macaulay duration
    macaulay_duration = macaulay_numerator / price

    # Modified duration
    modified_duration = macaulay_duration / (1.0 + yield_per_period)

    # Convexity
    convexity = convexity_numerator / (price * (1.0 + yield_per_period) ** 2)

    return BondPricingResult(
        price=price,
        macaulay_duration=macaulay_duration,
        modified_duration=modified_duration,
        convexity=convexity,
        yield_to_maturity=yield_to_maturity,
        spread_bps=spread_bps,
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
    total_yield = yield_to_maturity + spread_bps / 10_000.0

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
