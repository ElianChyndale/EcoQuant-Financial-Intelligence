"""Split-conformal abstention using nonconformity scores."""

from __future__ import annotations


def conformal_accept(*, score: float, threshold: float) -> bool:
    """Return True when the nonconformity score meets or exceeds the threshold."""
    return score >= threshold
