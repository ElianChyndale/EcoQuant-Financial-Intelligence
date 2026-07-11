"""Valuation policy engine: maps decision codes and risk factors to spread/haircut adjustments.

All outputs are model-driven parameters, not investment recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass

from ecoquant.uncertainty.decision import DecisionCode


@dataclass(frozen=True)
class PolicyInput:
    """Input bundle for the valuation policy function.

    Attributes:
        decision_code: The gating decision from the uncertainty module.
        evidence_ids: Ordered evidence identifiers supporting the decision.
        risk_factors: Mapping of factor name to normalised risk score in [0, 1].
        extraction_valid: Whether the upstream document extraction succeeded.
        base_spread_bps: Starting credit spread in basis points.
        max_spread_delta_bps: Upper bound on any single-channel spread adjustment.
        max_haircut_bps: Upper bound on the recommended haircut.
    """

    decision_code: DecisionCode
    evidence_ids: tuple[str, ...]
    risk_factors: dict[str, float]
    extraction_valid: bool
    base_spread_bps: int = 145
    max_spread_delta_bps: int = 50
    max_haircut_bps: int = 500


@dataclass(frozen=True)
class PolicyResult:
    """Output of the valuation policy function.

    Attributes:
        adjusted_spread_bps: Final spread after all adjustments.
        recommended_haircut_bps: Haircut recommendation (None when not auto-reportable).
        decision_code: The decision code that was applied.
        adjustments: Per-channel basis-point adjustments (empty when blocked).
    """

    adjusted_spread_bps: int
    recommended_haircut_bps: int | None
    decision_code: DecisionCode
    adjustments: dict[str, int]


def _clamp(value: int, lo: int, hi: int) -> int:
    """Constrain *value* to [lo, hi]."""
    return max(lo, min(hi, value))


def _compute_channel_adjustments(
    risk_factors: dict[str, float],
    max_delta: int,
) -> dict[str, int]:
    """Map each risk factor to a spread adjustment in [0, max_delta].

    The mapping is monotonically increasing: a higher risk factor score
    produces a larger (or equal) adjustment.  A factor value of 1.0 maps
    exactly to *max_delta*; 0.0 maps to 0.
    """
    adjustments: dict[str, int] = {}
    for factor, score in risk_factors.items():
        # Ensure score is within expected bounds before scaling.
        clamped_score = max(0.0, min(1.0, score))
        raw_bps = int(round(clamped_score * max_delta))
        adjustments[factor] = _clamp(raw_bps, 0, max_delta)
    return adjustments


def _compute_haircut(
    risk_factors: dict[str, float],
    max_haircut_bps: int,
) -> int:
    """Derive a haircut from the mean of all risk factors, capped at *max_haircut_bps*.

    Returns 0 when there are no risk factors.
    """
    if not risk_factors:
        return 0
    mean_risk = sum(max(0.0, min(1.0, s)) for s in risk_factors.values()) / len(
        risk_factors,
    )
    raw = int(round(mean_risk * max_haircut_bps))
    return _clamp(raw, 0, max_haircut_bps)


def apply_policy(inp: PolicyInput) -> PolicyResult:
    """Evaluate the valuation policy and return spread/haircut adjustments.

    Decision precedence (mirrors :func:`ecoquant.uncertainty.decision.decide`):

    1. **INSUFFICIENT_EVIDENCE** or invalid extraction -- no adjustment applied.
    2. **HUMAN_REVIEW_REQUIRED** -- bounded spread adjustments (capped at
       ``max_spread_delta_bps * 0.5``); no haircut recommendation.
    3. **AUTO_REPORT** -- full spread adjustments; haircut derived from risk
       factors and capped at ``max_haircut_bps``.

    All adjustments are monotonically related to risk factor values and
    individually bounded by ``max_spread_delta_bps``.

    Args:
        inp: The policy input bundle.

    Returns:
        A :class:`PolicyResult` with the adjusted spread, optional haircut,
        the governing decision code, and per-channel adjustments.
    """
    # ---- Gate 1: block if evidence is missing or extraction failed ----------
    if (
        inp.decision_code == DecisionCode.INSUFFICIENT_EVIDENCE
        or not inp.extraction_valid
    ):
        return PolicyResult(
            adjusted_spread_bps=inp.base_spread_bps,
            recommended_haircut_bps=None,
            decision_code=DecisionCode.INSUFFICIENT_EVIDENCE,
            adjustments={},
        )

    # ---- Gate 2: human review -- partial adjustments, no haircut ------------
    if inp.decision_code == DecisionCode.HUMAN_REVIEW_REQUIRED:
        half_cap = inp.max_spread_delta_bps // 2
        adjustments = _compute_channel_adjustments(inp.risk_factors, half_cap)
        total_delta = sum(adjustments.values())
        total_delta = _clamp(total_delta, 0, inp.max_spread_delta_bps)
        return PolicyResult(
            adjusted_spread_bps=inp.base_spread_bps + total_delta,
            recommended_haircut_bps=None,
            decision_code=DecisionCode.HUMAN_REVIEW_REQUIRED,
            adjustments=adjustments,
        )

    # ---- Gate 3: auto-report -- full adjustments + haircut ------------------
    adjustments = _compute_channel_adjustments(
        inp.risk_factors, inp.max_spread_delta_bps,
    )
    total_delta = sum(adjustments.values())
    total_delta = _clamp(total_delta, 0, inp.max_spread_delta_bps)
    haircut = _compute_haircut(inp.risk_factors, inp.max_haircut_bps)
    return PolicyResult(
        adjusted_spread_bps=inp.base_spread_bps + total_delta,
        recommended_haircut_bps=haircut,
        decision_code=DecisionCode.AUTO_REPORT,
        adjustments=adjustments,
    )
