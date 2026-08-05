from __future__ import annotations

import math

import pytest

from ecoquant.research.calibration_eval.evaluate import (
    coverage_at_precision,
    evaluate_selective_folds,
    risk_coverage_frontier,
)
from ecoquant.uncertainty.features import UncertaintyFeatures


def _synthetic_fold_data() -> dict[str, tuple[list[UncertaintyFeatures], list[bool]]]:
    """4 issuers x 4 records each; each issuer has both correct and wrong labels."""
    return {
        "A": (
            [UncertaintyFeatures(0.9, 1.0, 0.95, 1.0, 1.0),
             UncertaintyFeatures(0.8, 1.0, 0.85, 1.0, 0.8),
             UncertaintyFeatures(0.7, 0.5, 0.75, 1.0, 0.6),
             UncertaintyFeatures(0.6, 0.5, 0.65, 0.0, 0.5)],
            [True, True, True, False],
        ),
        "B": (
            [UncertaintyFeatures(0.9, 1.0, 0.9, 1.0, 1.0),
             UncertaintyFeatures(0.8, 1.0, 0.8, 1.0, 0.9),
             UncertaintyFeatures(0.7, 0.5, 0.7, 1.0, 0.7),
             UncertaintyFeatures(0.5, 0.0, 0.5, 0.0, 0.4)],
            [True, True, False, False],
        ),
        "C": (
            [UncertaintyFeatures(0.9, 1.0, 0.9, 1.0, 1.0),
             UncertaintyFeatures(0.8, 1.0, 0.8, 1.0, 0.9),
             UncertaintyFeatures(0.7, 0.5, 0.7, 1.0, 0.7),
             UncertaintyFeatures(0.5, 0.0, 0.5, 0.0, 0.4)],
            [True, True, False, False],
        ),
        "D": (
            [UncertaintyFeatures(0.9, 1.0, 0.9, 1.0, 1.0),
             UncertaintyFeatures(0.8, 1.0, 0.8, 1.0, 0.9),
             UncertaintyFeatures(0.7, 0.5, 0.7, 1.0, 0.7),
             UncertaintyFeatures(0.5, 0.0, 0.5, 0.0, 0.4)],
            [True, False, False, False],
        ),
    }


def test_evaluate_selective_folds_output_shape() -> None:
    result = evaluate_selective_folds(_synthetic_fold_data())
    assert "fold_count" in result
    assert "pooled_accuracy" in result
    assert "ece" in result
    assert "brier" in result
    assert "auc" in result
    assert 0.0 <= result["ece"] <= 1.0
    assert 0.0 <= result["brier"] <= 1.0


def test_risk_coverage_frontier_is_monotonic() -> None:
    probs = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05]
    labels = [True, True, True, True, True, False, False, False, False, False]
    frontier = risk_coverage_frontier(probs, labels)
    assert frontier  # non-empty
    # As threshold descends, coverage increases (accept more records).
    coverages = [point["coverage"] for point in frontier]
    assert coverages == sorted(coverages)
    # The highest threshold (0.9) accepts only the top record.
    assert frontier[0]["coverage"] == pytest.approx(0.1)
    # The lowest threshold (0.05) accepts all records.
    assert frontier[-1]["coverage"] == pytest.approx(1.0)


def test_coverage_at_precision() -> None:
    probs = [0.99, 0.95, 0.90, 0.85, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30]
    labels = [True, True, True, True, True, True, False, False, False, False]
    # At 90% precision target: accept top 6 (all True) = 60% coverage
    result = coverage_at_precision(probs, labels, target_precision=0.9)
    assert result["coverage"] == pytest.approx(0.6, abs=0.11)
    assert result["precision"] >= 0.9


def test_coverage_at_precision_impossible() -> None:
    probs = [0.5, 0.5, 0.5]
    labels = [False, False, False]
    result = coverage_at_precision(probs, labels, target_precision=0.9)
    assert result["coverage"] == 0.0
    assert result["reachable"] is False
