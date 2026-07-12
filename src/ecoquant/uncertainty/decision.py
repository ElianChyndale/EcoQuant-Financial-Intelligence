"""Strict decision gating with fixed precedence rules.

Precedence (highest to lowest):
  1. INSUFFICIENT_EVIDENCE (code 0) - invalid extraction or missing evidence
  2. HUMAN_REVIEW_REQUIRED (code 1) - evidence present but not auto-reportable
  3. AUTO_REPORT (code 2) - calibrated, conformal, and sufficient evidence

Non-finite calibrated probabilities (NaN, infinity) cannot produce AUTO_REPORT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

from .conformal import candidate_correctness_nonconformity, conformal_accept


class DecisionCode(IntEnum):
    """Three fixed decision codes with strict ordering."""

    INSUFFICIENT_EVIDENCE = 0
    HUMAN_REVIEW_REQUIRED = 1
    AUTO_REPORT = 2


@dataclass(frozen=True)
class Decision:
    """A gated decision with its code and reason."""

    code: DecisionCode
    reason: str


@dataclass(frozen=True)
class DecisionPolicy:
    """All thresholds frozen before an outer issuer is evaluated."""

    calibrated_probability_threshold: float
    conformal_threshold: float
    evidence_sufficiency_threshold: float

    def __post_init__(self) -> None:
        for name, value in (
            ("calibrated_probability_threshold", self.calibrated_probability_threshold),
            ("conformal_threshold", self.conformal_threshold),
            ("evidence_sufficiency_threshold", self.evidence_sufficiency_threshold),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")


def decide(
    calibrated_probability: float,
    evidence_sufficiency: float,
    extraction_valid: bool,
    temporal_valid: bool,
    policy: DecisionPolicy,
) -> Decision:
    """Apply strict decision precedence to calibrated model outputs.

    Args:
        calibrated_probability: Platt-calibrated correctness probability.
        evidence_sufficiency: Fraction of required evidence present [0, 1].
        extraction_valid: Whether the extraction succeeded without errors.
        temporal_valid: Whether the evidence is valid at the requested time.
        policy: Fold-specific thresholds frozen before outer evaluation.

    Returns:
        A Decision with the highest-precedence applicable code.
    """

    # Highest precedence: invalid extraction or missing evidence.
    if not extraction_valid:
        return Decision(DecisionCode.INSUFFICIENT_EVIDENCE, "extraction_invalid")

    # Check finiteness BEFORE any comparison.
    # Non-finite evidence sufficiency cannot be compared to a threshold.
    if not math.isfinite(evidence_sufficiency):
        return Decision(DecisionCode.INSUFFICIENT_EVIDENCE, "non_finite_evidence")

    if evidence_sufficiency < policy.evidence_sufficiency_threshold:
        return Decision(DecisionCode.INSUFFICIENT_EVIDENCE, "evidence_insufficient")

    # Reject non-finite calibrated probabilities (NaN, infinity, missing).
    # These cannot produce AUTO_REPORT.
    if not math.isfinite(calibrated_probability):
        return Decision(DecisionCode.HUMAN_REVIEW_REQUIRED, "non_finite_probability")

    if not 0.0 <= calibrated_probability <= 1.0:
        return Decision(DecisionCode.HUMAN_REVIEW_REQUIRED, "probability_out_of_range")

    if not temporal_valid:
        return Decision(DecisionCode.HUMAN_REVIEW_REQUIRED, "temporal_gate_failed")

    nonconformity_score = candidate_correctness_nonconformity(calibrated_probability)
    conforms = conformal_accept(
        score=nonconformity_score,
        threshold=policy.conformal_threshold,
    )

    # AUTO_REPORT requires all three gates: calibrated probability, conformal
    # acceptance, and sufficient evidence coverage.
    if (
        calibrated_probability >= policy.calibrated_probability_threshold
        and conforms
        and evidence_sufficiency >= policy.evidence_sufficiency_threshold
    ):
        return Decision(DecisionCode.AUTO_REPORT, "calibrated_conformal_sufficient")

    # Everything else requires human review.
    return Decision(DecisionCode.HUMAN_REVIEW_REQUIRED, "below_auto_gate")
