"""Scenario-specific sensitivity analysis for valuation adjustments.

Every output is a **model sensitivity estimate**, not an investment
recommendation.  Consumers must treat results as indicative only.

Uses proper bond pricing with duration and convexity calculations.
Unknown risk mappings return explicit results and cannot change spread.
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
        evidence_id: Actual evidence identifier (not risk-factor name).
        issuer: Bond issuer.
        bond_id: Bond or asset identifier.
        risk_factor: The risk factor name that drove this adjustment.
        risk_channel: The mapped risk channel for this factor.
        rule_id: Version of the policy rule applied.
        rule_version: Version of the policy rule applied.
        units: Units for spread values (always "bps").
        base_spread_bps: Base credit spread before this channel adjustment.
        spread_delta_bps: The spread adjustment applied for this channel.
        adjusted_spread_bps: Total adjusted spread (base + delta).
        decision_code: The governing decision code from the policy result.
        base_price: Price before spread shock.
        adjusted_clean_price: Clean price after applying the spread shock.
        adjusted_dirty_price: Dirty price after applying the spread shock.
        adjusted_duration: Duration after applying the spread shock.
        adjusted_convexity: Convexity after applying the spread shock.
        valid_time: Valid time of the evidence.
        source_time: Source/publication time of the evidence.
        status: Status of the mapping ("adjusted", "unsupported_risk_mapping",
            "no_adjustment", "insufficient_evidence").
    """

    scenario_name: str
    evidence_id: str
    issuer: str
    bond_id: str
    risk_factor: str
    risk_channel: str
    rule_id: str
    rule_version: str
    units: str
    base_spread_bps: int
    spread_delta_bps: int
    adjusted_spread_bps: int
    decision_code: DecisionCode
    base_price: float
    adjusted_clean_price: float
    adjusted_dirty_price: float
    adjusted_duration: float
    adjusted_convexity: float
    valid_time: str
    source_time: str
    status: str


@dataclass(frozen=True)
class UnsupportedMapping:
    """Result for a risk factor with no channel mapping.

    Unsupported mappings cannot change spread or haircut.
    """

    risk_factor: str
    status: str = "unsupported_risk_mapping"


@dataclass(frozen=True)
class ValuationSensitivityResult:
    """Complete sensitivity analysis result."""

    base_price: float
    base_clean_price: float
    base_dirty_price: float
    base_duration: float
    base_convexity: float
    scenarios: tuple[SensitivityScenario, ...]
    unsupported_mappings: tuple[UnsupportedMapping, ...]
    bond_terms: BondTerms
    base_yield: float
    base_spread_bps: int


def compute_sensitivity(
    bond_terms: BondTerms,
    base_yield: float,
    base_spread_bps: int,
    policy_result: PolicyResult,
    risk_channel_map: dict[str, str],
    *,
    issuer: str = "",
    bond_id: str = "",
    evidence_id: str = "",
    rule_id: str = "v1",
    rule_version: str = "v1",
    valid_time: str = "",
    source_time: str = "",
) -> ValuationSensitivityResult:
    """Generate one sensitivity scenario per active adjustment channel.

    For each entry in ``policy_result.adjustments`` the function:

    1. Looks up the corresponding risk channel via *risk_channel_map*.
    2. If no mapping exists, records an UnsupportedMapping (cannot change spread).
    3. If mapping exists, computes the bond price with the spread shock applied.
    4. Records the adjusted price, duration, and convexity with full provenance.

    Unknown risk-channel mappings are NOT silently skipped. They are recorded
    as unsupported and cannot change spread or haircut.

    Args:
        bond_terms: Bond terms for pricing.
        base_yield: Base yield without spread.
        base_spread_bps: Base credit spread in bps.
        policy_result: Output of :func:`~ecoquant.valuation.policy.apply_policy`.
        risk_channel_map: Mapping from risk factor name to risk channel name.
        issuer: Bond issuer name.
        bond_id: Bond or asset identifier.
        evidence_id: Actual evidence identifier.
        rule_id: Policy rule identifier.
        rule_version: Policy rule version.
        valid_time: Valid time of the evidence.
        source_time: Source/publication time of the evidence.

    Returns:
        A ValuationSensitivityResult with base pricing, per-channel scenarios,
        and unsupported mappings.

    Note:
        Results represent model sensitivity estimates only and must not be
        treated as investment advice.
    """
    # Validate inputs
    if not math.isfinite(base_yield):
        raise ValueError(f"base_yield must be finite, got {base_yield}")
    if not math.isfinite(base_spread_bps):
        raise ValueError(f"base_spread_bps must be finite, got {base_spread_bps}")

    # Compute base pricing
    base_pricing = price_bond(bond_terms, base_yield, base_spread_bps)

    scenarios: list[SensitivityScenario] = []
    unsupported: list[UnsupportedMapping] = []

    for factor, delta_bps in policy_result.adjustments.items():
        channel = risk_channel_map.get(factor)
        if channel is None:
            # No channel mapping available — record as unsupported.
            # Cannot change spread or haircut.
            unsupported.append(UnsupportedMapping(risk_factor=factor))
            continue

        # Compute pricing with spread shock
        shocked_pricing = price_bond_with_spread_shock(
            bond_terms, base_yield, base_spread_bps, delta_bps
        )

        scenarios.append(
            SensitivityScenario(
                scenario_name=f"sensitivity_{channel}",
                evidence_id=evidence_id if evidence_id else factor,
                issuer=issuer,
                bond_id=bond_id,
                risk_factor=factor,
                risk_channel=channel,
                rule_id=rule_id,
                rule_version=rule_version,
                units="bps",
                base_spread_bps=base_spread_bps,
                spread_delta_bps=delta_bps,
                adjusted_spread_bps=base_spread_bps + delta_bps,
                decision_code=policy_result.decision_code,
                base_price=base_pricing.price,
                adjusted_clean_price=shocked_pricing.clean_price,
                adjusted_dirty_price=shocked_pricing.price,
                adjusted_duration=shocked_pricing.modified_duration,
                adjusted_convexity=shocked_pricing.convexity,
                valid_time=valid_time,
                source_time=source_time,
                status="adjusted",
            ),
        )

    return ValuationSensitivityResult(
        base_price=base_pricing.price,
        base_clean_price=base_pricing.clean_price,
        base_dirty_price=base_pricing.price,
        base_duration=base_pricing.modified_duration,
        base_convexity=base_pricing.convexity,
        scenarios=tuple(scenarios),
        unsupported_mappings=tuple(unsupported),
        bond_terms=bond_terms,
        base_yield=base_yield,
        base_spread_bps=base_spread_bps,
    )


# Import math for validation
import math
