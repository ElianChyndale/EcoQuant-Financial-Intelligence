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


# Frozen thresholds for the decision gate.
_MIN_EVIDENCE_SUFFICIENCY: float = 0.25
_MIN_CALIBRATED_PROBABILITY: float = 0.70


def decide(
    calibrated_probability: float,
    conforms: bool,
    evidence_sufficiency: float,
    extraction_valid: bool,
) -> Decision:
    """Apply strict decision precedence to calibrated model outputs.

    Args:
        calibrated_probability: Platt-calibrated correctness probability.
        conforms: Whether the conformal acceptance test passes.
        evidence_sufficiency: Fraction of required evidence present [0, 1].
        extraction_valid: Whether the extraction succeeded without errors.

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

    if evidence_sufficiency < _MIN_EVIDENCE_SUFFICIENCY:
        return Decision(DecisionCode.INSUFFICIENT_EVIDENCE, "evidence_insufficient")

    # Reject non-finite calibrated probabilities (NaN, infinity, missing).
    # These cannot produce AUTO_REPORT.
    if not math.isfinite(calibrated_probability):
        return Decision(DecisionCode.HUMAN_REVIEW_REQUIRED, "non_finite_probability")

    # AUTO_REPORT requires all three gates: calibrated probability, conformal
    # acceptance, and sufficient evidence coverage.
    if (
        calibrated_probability >= _MIN_CALIBRATED_PROBABILITY
        and conforms
        and evidence_sufficiency >= _MIN_EVIDENCE_SUFFICIENCY
    ):
        return Decision(DecisionCode.AUTO_REPORT, "calibrated_conformal_sufficient")

    # Everything else requires human review.
    return Decision(DecisionCode.HUMAN_REVIEW_REQUIRED, "below_auto_gate")
