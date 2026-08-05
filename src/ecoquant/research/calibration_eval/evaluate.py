"""E5: calibrated selective prediction evaluation over held-out folds.

Reuses the existing calibrated-abstention machinery:
``fit_calibration_folds`` (nested leave-one-issuer-out), ``brier_score``,
``expected_calibration_error``, ``risk_coverage_curve``. Adds:

- pooling held-out fold probabilities/labels into one risk-coverage frontier,
- ``coverage_at_precision`` — the E5 headline metric: at what coverage can the
  system auto-accept with a target supported-answer precision?
- ``evaluate_selective_folds`` — the one-call entry point.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from ecoquant.uncertainty.calibration import (
    brier_score,
    expected_calibration_error,
    fit_calibration_folds,
    risk_coverage_curve,
)
from ecoquant.uncertainty.features import UncertaintyFeatures


def evaluate_selective_folds(
    fold_data: Mapping[str, tuple[list[UncertaintyFeatures], list[bool]]],
    *,
    conformal_alpha: float = 0.10,
    max_selective_error: float = 0.10,
    seed: int = 20260710,
) -> dict[str, object]:
    """Fit nested folds and evaluate pooled held-out selective performance."""
    if len(fold_data) < 4:
        raise ValueError("evaluate_selective_folds requires at least four issuers")
    folds = fit_calibration_folds(
        dict(fold_data),
        conformal_alpha=conformal_alpha,
        max_selective_error=max_selective_error,
        seed=seed,
    )

    # Pool held-out probabilities/labels across folds (each record evaluated once).
    pooled_probs: list[float] = []
    pooled_labels: list[bool] = []
    for fold in folds:
        pooled_probs.extend(fold.test_probs)
        pooled_labels.extend(fold.test_labels)

    accuracy = sum(pooled_labels) / len(pooled_labels) if pooled_labels else 0.0
    ece = expected_calibration_error(pooled_probs, pooled_labels)
    brier = brier_score(pooled_probs, pooled_labels)
    auc = _auc(pooled_probs, pooled_labels)
    frontier = risk_coverage_frontier(pooled_probs, pooled_labels)
    cov90 = coverage_at_precision(pooled_probs, pooled_labels, target_precision=0.90)
    cov95 = coverage_at_precision(pooled_probs, pooled_labels, target_precision=0.95)

    return {
        "fold_count": len(folds),
        "pooled_accuracy": accuracy,
        "ece": ece,
        "brier": brier,
        "auc": auc,
        "coverage_at_90pct_precision": cov90,
        "coverage_at_95pct_precision": cov95,
        "risk_coverage_frontier": frontier,
    }


def risk_coverage_frontier(
    probs: Sequence[float],
    labels: Sequence[bool],
) -> list[dict[str, float]]:
    """Coverage and risk at every distinct probability threshold, descending."""
    if len(probs) != len(labels):
        raise ValueError("probabilities and labels must align")
    paired = sorted(zip(probs, labels), key=lambda item: -item[0])
    frontier: list[dict[str, float]] = []
    n = len(paired)
    for i in range(n):
        threshold = paired[i][0]
        accepted = [label for _, label in paired[: i + 1]]
        coverage = (i + 1) / n
        risk = 1.0 - sum(accepted) / len(accepted)
        frontier.append({"threshold": threshold, "coverage": coverage, "risk": risk})
    return frontier


def coverage_at_precision(
    probs: Sequence[float],
    labels: Sequence[bool],
    *,
    target_precision: float,
) -> dict[str, float | bool]:
    """Maximum coverage reachable while keeping auto-accept precision >= target.

    Accepts records in descending probability order until adding the next
    record would drop precision below ``target_precision``.
    """
    if not 0.0 < target_precision <= 1.0:
        raise ValueError("target_precision must be in (0, 1]")
    if len(probs) != len(labels):
        raise ValueError("probabilities and labels must align")
    paired = sorted(zip(probs, labels), key=lambda item: -item[0])
    n = len(paired)
    best_coverage = 0.0
    best_precision = 0.0
    reachable = False
    for i in range(n):
        accepted = [label for _, label in paired[: i + 1]]
        precision = sum(accepted) / len(accepted)
        if precision >= target_precision:
            best_coverage = (i + 1) / n
            best_precision = precision
            reachable = True
        else:
            break  # precision decreases as we accept more; stop at first miss
    return {
        "coverage": best_coverage,
        "precision": best_precision,
        "target_precision": target_precision,
        "reachable": reachable,
    }


def _auc(probs: Sequence[float], labels: Sequence[bool]) -> float:
    """Area under ROC for correctness (rank-based; ties broken by label)."""
    if len(probs) != len(labels):
        raise ValueError("probabilities and labels must align")
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return 0.5
    paired = sorted(zip(probs, labels), key=lambda item: (item[0], item[1]))
    rank_sum = sum(
        rank for rank, (_, label) in enumerate(paired, start=1) if label
    )
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)
