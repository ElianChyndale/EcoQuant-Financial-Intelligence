"""Scenario-specific sensitivity analysis for valuation adjustments.

Every output is a **model sensitivity estimate**, not an investment
recommendation.  Consumers must treat results as indicative only.

Uses proper bond pricing with duration and convexity calculations.
"""

from __future__ import annotations

from dataclasses import dataclass

from ecoquant.uncertainty.decision import DecisionCode
from ecoquant.valuation.policy import PolicyResult
from ecoquant.valuation.bond_pricing import (
    BondTerms,
    BondPricingResult,
    price_bond,
    price_bond_with_spread_shock,
)


@dataclass(frozen=True)
class SensitivityScenario:
    """Result of perturbing base valuation parameters along a single risk channel.

    Attributes:
        scenario_name: Human-readable label for the risk channel.
        evidence_id: Identifier linking back to the originating risk factor.
        risk_factor: The risk factor name that drove this adjustment.
        risk_channel: The mapped risk channel for this factor.
        units: Units for spread values (always "bps").
        base_spread_bps: Base credit spread before this channel adjustment.
        spread_delta_bps: The spread adjustment applied for this channel.
        adjusted_spread_bps: Total adjusted spread (base + delta).
        decision_code: The governing decision code from the policy result.
        adjusted_price: Price after applying the spread shock.
        adjusted_duration: Duration after applying the spread shock.
        adjusted_convexity: Convexity after applying the spread shock.
        rule_version: Version of the policy rule applied.
    """

    scenario_name: str
    evidence_id: str
    risk_factor: str
    risk_channel: str
    units: str
    base_spread_bps: int
    spread_delta_bps: int
    adjusted_spread_bps: int
    decision_code: DecisionCode
    adjusted_price: float
    adjusted_duration: float
    adjusted_convexity: float
    rule_version: str = "v1"


@dataclass(frozen=True)
class ValuationSensitivityResult:
    """Complete sensitivity analysis result."""

    base_price: float
    base_duration: float
    base_convexity: float
    scenarios: tuple[SensitivityScenario, ...]
    bond_terms: BondTerms
    base_yield: float
    base_spread_bps: int


def compute_sensitivity(
    bond_terms: BondTerms,
    base_yield: float,
    base_spread_bps: int,
    policy_result: PolicyResult,
    risk_channel_map: dict[str, str],
) -> ValuationSensitivityResult:
    """Generate one sensitivity scenario per active adjustment channel.

    For each entry in ``policy_result.adjustments`` the function:

    1. Looks up the corresponding risk channel via *risk_channel_map*.
    2. Computes the bond price with the spread shock applied.
    3. Records the adjusted price, duration, and convexity.

    Factors present in the adjustments but absent from *risk_channel_map*
    are skipped silently (they have no channel to attribute the shock to).

    Args:
        bond_terms: Bond terms for pricing.
        base_yield: Base yield without spread.
        base_spread_bps: Base credit spread in bps.
        policy_result: Output of :func:`~ecoquant.valuation.policy.apply_policy`.
        risk_channel_map: Mapping from risk factor name to risk channel name.

    Returns:
        A ValuationSensitivityResult with base pricing and per-channel scenarios.

    Note:
        Results represent model sensitivity estimates only and must not be
        treated as investment advice.
    """
    # Compute base pricing
    base_pricing = price_bond(bond_terms, base_yield, base_spread_bps)

    scenarios: list[SensitivityScenario] = []

    for factor, delta_bps in policy_result.adjustments.items():
        channel = risk_channel_map.get(factor)
        if channel is None:
            # No channel mapping available -- skip this factor.
            continue

        # Compute pricing with spread shock
        shocked_pricing = price_bond_with_spread_shock(
            bond_terms, base_yield, base_spread_bps, delta_bps
        )

        scenarios.append(
            SensitivityScenario(
                scenario_name=f"sensitivity_{channel}",
                evidence_id=factor,
                risk_factor=factor,
                risk_channel=channel,
                units="bps",
                base_spread_bps=base_spread_bps,
                spread_delta_bps=delta_bps,
                adjusted_spread_bps=base_spread_bps + delta_bps,
                decision_code=policy_result.decision_code,
                adjusted_price=shocked_pricing.price,
                adjusted_duration=shocked_pricing.modified_duration,
                adjusted_convexity=shocked_pricing.convexity,
            ),
        )

    return ValuationSensitivityResult(
        base_price=base_pricing.price,
        base_duration=base_pricing.modified_duration,
        base_convexity=base_pricing.convexity,
        scenarios=tuple(scenarios),
        bond_terms=bond_terms,
        base_yield=base_yield,
        base_spread_bps=base_spread_bps,
    )
