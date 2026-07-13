"""Valuation policy engine: maps decision codes and risk factors to spread/haircut adjustments.

All outputs are model-driven parameters, not investment recommendations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

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
    risk_channel_map: dict[str, str] = field(default_factory=dict)
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
    unsupported_risk_factors: tuple[str, ...] = ()


def _clamp(value: int, lo: int, hi: int) -> int:
    """Constrain *value* to [lo, hi]."""
    return max(lo, min(hi, value))


def _validate_policy_input(inp: PolicyInput) -> None:
    if not isinstance(inp.decision_code, DecisionCode):
        raise TypeError("decision_code must be a DecisionCode")
    if type(inp.extraction_valid) is not bool:
        raise TypeError("extraction_valid must be bool")
    if not isinstance(inp.evidence_ids, tuple) or any(
        not isinstance(identifier, str) or not identifier
        for identifier in inp.evidence_ids
    ):
        raise ValueError("evidence_ids must be a tuple of non-empty strings")
    if not isinstance(inp.risk_factors, dict):
        raise TypeError("risk_factors must be a dict")
    for factor, score in inp.risk_factors.items():
        if not isinstance(factor, str) or not factor:
            raise ValueError("risk factor names must be non-empty strings")
        if not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("risk factor scores must be finite")
        if not 0.0 <= score <= 1.0:
            raise ValueError("risk factor scores must be within [0, 1]")
    if not isinstance(inp.risk_channel_map, dict):
        raise TypeError("risk_channel_map must be a dict")
    for factor, channel in inp.risk_channel_map.items():
        if not isinstance(factor, str) or not factor:
            raise ValueError("risk channel factor names must be non-empty strings")
        if not isinstance(channel, str) or not channel:
            raise ValueError("risk channel names must be non-empty strings")
    for name, value in (
        ("base_spread_bps", inp.base_spread_bps),
        ("max_spread_delta_bps", inp.max_spread_delta_bps),
        ("max_haircut_bps", inp.max_haircut_bps),
    ):
        if type(value) is not int:
            raise TypeError(f"{name} must be integer basis points")
        if value < 0:
            raise ValueError(f"{name} must be non-negative bps")


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
    _validate_policy_input(inp)
    supported_risk_factors = {
        factor: score
        for factor, score in inp.risk_factors.items()
        if factor in inp.risk_channel_map
    }
    unsupported_risk_factors = tuple(
        sorted(set(inp.risk_factors) - set(supported_risk_factors))
    )

    # ---- Gate 1: block if evidence is missing or extraction failed ----------
    if (
        inp.decision_code == DecisionCode.INSUFFICIENT_EVIDENCE
        or not inp.extraction_valid
        or not inp.evidence_ids
    ):
        return PolicyResult(
            adjusted_spread_bps=inp.base_spread_bps,
            recommended_haircut_bps=None,
            decision_code=DecisionCode.INSUFFICIENT_EVIDENCE,
            adjustments={},
            unsupported_risk_factors=(),
        )

    # ---- Gate 2: human review -- partial adjustments, no haircut ------------
    if inp.decision_code == DecisionCode.HUMAN_REVIEW_REQUIRED:
        half_cap = inp.max_spread_delta_bps // 2
        adjustments = _compute_channel_adjustments(supported_risk_factors, half_cap)
        total_delta = sum(adjustments.values())
        total_delta = _clamp(total_delta, 0, inp.max_spread_delta_bps)
        return PolicyResult(
            adjusted_spread_bps=inp.base_spread_bps + total_delta,
            recommended_haircut_bps=None,
            decision_code=DecisionCode.HUMAN_REVIEW_REQUIRED,
            adjustments=adjustments,
            unsupported_risk_factors=unsupported_risk_factors,
        )

    # ---- Gate 3: auto-report -- full adjustments + haircut ------------------
    adjustments = _compute_channel_adjustments(
        supported_risk_factors, inp.max_spread_delta_bps,
    )
    total_delta = sum(adjustments.values())
    total_delta = _clamp(total_delta, 0, inp.max_spread_delta_bps)
    haircut = _compute_haircut(supported_risk_factors, inp.max_haircut_bps)
    return PolicyResult(
        adjusted_spread_bps=inp.base_spread_bps + total_delta,
        recommended_haircut_bps=haircut,
        decision_code=DecisionCode.AUTO_REPORT,
        adjustments=adjustments,
        unsupported_risk_factors=unsupported_risk_factors,
    )
