"""Split-conformal abstention using nonconformity scores.

Implements a documented split-conformal prediction protocol.

Protocol
--------
- **Nonconformity score**: larger values mean *worse* conformity (i.e., the
  prediction is less conforming to the calibration distribution).
- **Score direction**: larger-is-worse.  Acceptance requires
  ``score <= threshold``.
- **Calibration population**: scores from the inner calibration split,
  never from outer held-out data.
- **Target alpha**: the desired miscoverage rate (e.g., 0.10 for 90% coverage).
- **Finite-sample quantile index**: ``k = ceil((n + 1) * (1 - alpha))``,
  clamped to ``[1, n]``.
- **Tie handling**: the quantile is computed over sorted values; ties at the
  boundary are included (standard right-inclusive convention).
- **Small-sample handling**: for ``n >= 1`` the quantile is well-defined.
  For ``n = 0`` the function raises ``ValueError``.
- **Empty-calibration behavior**: raises ``ValueError`` — no threshold can
  be computed from an empty calibration set.

Acceptance criteria
-------------------
A prediction is accepted when its nonconformity score is **less than or equal
to** the calibrated threshold.  The following are always **rejected**:

- NaN scores
- positive infinity
- negative infinity
- missing (None) scores
- missing (None/NaN) thresholds
- empty calibration data
"""

from __future__ import annotations

import math
from typing import Sequence


def correctness_nonconformity(
    calibrated_probability: float,
    *,
    observed_correct: bool,
) -> float:
    """Return the binary correctness nonconformity for a calibration row.

    The calibrated probability is the probability of the frozen target
    ``correct_and_supported``.  A correct observation has score ``1 - p``;
    an incorrect observation has score ``p``.  Larger scores are worse.
    """
    if not isinstance(calibrated_probability, (int, float)) or not math.isfinite(
        calibrated_probability
    ):
        raise ValueError("calibrated_probability must be finite")
    if not 0.0 <= calibrated_probability <= 1.0:
        raise ValueError("calibrated_probability must be within [0, 1]")
    if type(observed_correct) is not bool:
        raise TypeError("observed_correct must be bool")
    return 1.0 - calibrated_probability if observed_correct else calibrated_probability


def candidate_correctness_nonconformity(calibrated_probability: float) -> float:
    """Score the candidate label ``correct_and_supported=True`` at decision time."""
    return correctness_nonconformity(
        calibrated_probability,
        observed_correct=True,
    )


def compute_conformal_threshold(
    calibration_scores: Sequence[float],
    *,
    alpha: float,
) -> float:
    """Compute the split-conformal threshold from calibration nonconformity scores.

    Uses the finite-sample quantile rule:
        k = ceil((n + 1) * (1 - alpha))
    with safe clipping to [1, n].

    Args:
        calibration_scores: Nonconformity scores from the calibration set.
            All values must be finite.
        alpha: Target miscoverage rate in (0, 1).

    Returns:
        The conformal threshold (a finite float).

    Raises:
        ValueError: If calibration_scores is empty, alpha is not in (0, 1),
            or any score is non-finite.
    """
    if not calibration_scores:
        raise ValueError("calibration_scores must be non-empty")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    n = len(calibration_scores)

    # Validate all scores are finite
    for i, s in enumerate(calibration_scores):
        if not isinstance(s, (int, float)):
            raise TypeError(f"calibration_scores[{i}] must be numeric, got {type(s)}")
        if not math.isfinite(s):
            raise ValueError(f"calibration_scores[{i}] must be finite, got {s}")

    # Sort ascending
    sorted_scores = sorted(calibration_scores)

    # Finite-sample quantile index: k = ceil((n + 1) * (1 - alpha))
    # Clamped to [1, n] for safety
    raw_k = math.ceil((n + 1) * (1.0 - alpha))
    k = max(1, min(raw_k, n))

    # The threshold is the k-th smallest value (1-indexed)
    # In 0-indexed Python: index k-1
    threshold = sorted_scores[k - 1]

    if not math.isfinite(threshold):
        raise ValueError(f"computed threshold is non-finite: {threshold}")

    return threshold


def conformal_accept(
    *,
    score: float,
    threshold: float,
) -> bool:
    """Test whether a prediction's nonconformity score is accepted.

    For a larger-is-worse nonconformity score, acceptance requires
    ``score <= threshold``.

    The following are always **rejected** (return False):
    - NaN score or threshold
    - positive or negative infinity
    - missing (None) values

    Args:
        score: The nonconformity score for the prediction.
        threshold: The calibrated conformal threshold.

    Returns:
        True if the prediction is accepted, False otherwise.
    """
    # Reject None values
    if score is None or threshold is None:
        return False

    # Reject non-finite values
    if not isinstance(score, (int, float)) or not isinstance(threshold, (int, float)):
        return False

    if not math.isfinite(score) or not math.isfinite(threshold):
        return False

    # Larger-is-worse: accept iff score <= threshold
    return score <= threshold
