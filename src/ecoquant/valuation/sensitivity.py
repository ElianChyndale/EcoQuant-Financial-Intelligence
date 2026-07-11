"""Scenario-specific sensitivity analysis for valuation adjustments.

Every output is a **model sensitivity estimate**, not an investment
recommendation.  Consumers must treat results as indicative only.
"""

from __future__ import annotations

from dataclasses import dataclass

from ecoquant.uncertainty.decision import DecisionCode
from ecoquant.valuation.policy import PolicyResult


@dataclass(frozen=True)
class SensitivityScenario:
    """Result of perturbing base valuation parameters along a single risk channel.

    Attributes:
        scenario_name: Human-readable label for the risk channel.
        evidence_id: Identifier linking back to the originating risk factor.
        risk_factor: The risk factor name that drove this adjustment.
        risk_channel: The mapped risk channel for this factor.
        spread_delta_bps: The spread adjustment applied for this channel.
        decision_code: The governing decision code from the policy result.
        adjusted_price: Price after applying the spread shock.
        adjusted_duration: Duration scaled proportionally to the price change.
        adjusted_convexity: Convexity scaled proportionally to the price change.
    """

    scenario_name: str
    evidence_id: str
    risk_factor: str
    risk_channel: str
    spread_delta_bps: int
    decision_code: DecisionCode
    adjusted_price: float
    adjusted_duration: float
    adjusted_convexity: float


def compute_sensitivity(
    base_price: float,
    base_duration: float,
    base_convexity: float,
    policy_result: PolicyResult,
    risk_channel_map: dict[str, str],
) -> tuple[SensitivityScenario, ...]:
    """Generate one sensitivity scenario per active adjustment channel.

    For each entry in ``policy_result.adjustments`` the function:

    1. Looks up the corresponding risk channel via *risk_channel_map*.
    2. Computes the spread impact factor ``1 - delta_bps / 10_000``.
    3. Applies that factor uniformly to price, duration, and convexity.

    Factors present in the adjustments but absent from *risk_channel_map*
    are skipped silently (they have no channel to attribute the shock to).

    Args:
        base_price: Unadjusted clean price of the instrument.
        base_duration: Unadjusted modified duration (years).
        base_convexity: Unadjusted convexity measure.
        policy_result: Output of :func:`~ecoquant.valuation.policy.apply_policy`.
        risk_channel_map: Mapping from risk factor name to risk channel name.

    Returns:
        A tuple of :class:`SensitivityScenario` instances, one per mapped
        adjustment channel.  The tuple is empty when there are no adjustments
        or when no factors resolve to a channel.

    Note:
        Results represent model sensitivity estimates only and must not be
        treated as investment advice.
    """
    scenarios: list[SensitivityScenario] = []

    for factor, delta_bps in policy_result.adjustments.items():
        channel = risk_channel_map.get(factor)
        if channel is None:
            # No channel mapping available -- skip this factor.
            continue

        # Spread impact factor: positive delta_bps means spread widening,
        # which reduces the price proportionally.
        shock = 1.0 - delta_bps / 10_000.0

        adjusted_price = base_price * shock
        adjusted_duration = base_duration * shock
        adjusted_convexity = base_convexity * shock

        scenarios.append(
            SensitivityScenario(
                scenario_name=f"sensitivity_{channel}",
                evidence_id=factor,
                risk_factor=factor,
                risk_channel=channel,
                spread_delta_bps=delta_bps,
                decision_code=policy_result.decision_code,
                adjusted_price=adjusted_price,
                adjusted_duration=adjusted_duration,
                adjusted_convexity=adjusted_convexity,
            ),
        )

    return tuple(scenarios)
