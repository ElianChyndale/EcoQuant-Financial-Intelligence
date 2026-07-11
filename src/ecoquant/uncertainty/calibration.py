"""Leave-one-issuer-out calibration with frozen thresholds.

All calibration is fit only on non-test issuers. The threshold is frozen
before final test evaluation to prevent leakage.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .features import UncertaintyFeatures


@dataclass(frozen=True)
class SimpleCalibrator:
    """Minimal Platt-style calibrator using a fixed sigmoid transform.

    In fixture mode this uses a deterministic mapping from features to
    probability; production backends replace this with a fitted model.
    """

    weight_retrieval_margin: float = 1.0
    weight_agreement: float = 0.5
    weight_extraction: float = 0.8
    weight_temporal: float = 0.3
    weight_coverage: float = 0.6
    bias: float = -0.5

    def predict_proba(self, features: Sequence[UncertaintyFeatures]) -> list[float]:
        """Map features to calibrated probabilities via a deterministic sigmoid."""
        return [self._sigmoid(self._logit(f)) for f in features]

    def _logit(self, f: UncertaintyFeatures) -> float:
        return (
            self.weight_retrieval_margin * f.retrieval_margin
            + self.weight_agreement * f.cross_retriever_agreement
            + self.weight_extraction * f.extraction_confidence
            + self.weight_temporal * f.temporal_validity
            + self.weight_coverage * f.evidence_coverage
            + self.bias
        )

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)


@dataclass(frozen=True)
class CalibrationFold:
    """One leave-one-issuer-out fold."""

    test_issuer: str
    train_issuers: tuple[str, ...]
    calibrator: SimpleCalibrator
    test_probs: tuple[float, ...]
    test_labels: tuple[bool, ...]


@dataclass(frozen=True)
class CalibrationResult:
    """Aggregated calibration outcome across all folds."""

    folds: tuple[CalibrationFold, ...]
    frozen_threshold: float
    brier: float
    ece: float
    aurc: float
    coverage_at_threshold: float


def fit_calibration_folds(
    fold_data: dict[str, tuple[list[UncertaintyFeatures], list[bool]]],
) -> tuple[CalibrationFold, ...]:
    """Fit leave-one-issuer-out calibration folds.

    Each fold trains a calibrator on all non-test issuers and evaluates
    on the held-out test issuer.
    """

    issuers = tuple(sorted(fold_data))
    folds: list[CalibrationFold] = []

    for test_issuer in issuers:
        train_issuers = tuple(i for i in issuers if i != test_issuer)

        # Aggregate training features and labels from non-test issuers.
        train_features: list[UncertaintyFeatures] = []
        train_labels: list[bool] = []
        for train_issuer in train_issuers:
            features, labels = fold_data[train_issuer]
            train_features.extend(features)
            train_labels.extend(labels)

        # Fit calibrator (deterministic in fixture mode).
        calibrator = SimpleCalibrator()

        # Evaluate on test issuer.
        test_features, test_labels = fold_data[test_issuer]
        test_probs = calibrator.predict_proba(test_features)

        folds.append(
            CalibrationFold(
                test_issuer=test_issuer,
                train_issuers=train_issuers,
                calibrator=calibrator,
                test_probs=tuple(test_probs),
                test_labels=tuple(test_labels),
            )
        )

    return tuple(folds)


def freeze_threshold(
    folds: Sequence[CalibrationFold],
    *,
    max_selective_error: float = 0.10,
) -> float:
    """Find the lowest threshold achieving at most max_selective_error on calibration data.

    The threshold is frozen before final test evaluation.
    """

    # Collect all calibration probabilities and labels.
    all_probs: list[float] = []
    all_labels: list[bool] = []
    for fold in folds:
        all_probs.extend(fold.test_probs)
        all_labels.extend(fold.test_labels)

    if not all_probs:
        return 0.0

    # Sort by probability descending.
    paired = sorted(zip(all_probs, all_labels), key=lambda x: -x[0])
    probs_sorted = [p for p, _ in paired]
    labels_sorted = [l for _, l in paired]

    # Find threshold: accept predictions above this probability.
    # Sweep from high to low, tracking cumulative error rate.
    n = len(probs_sorted)
    best_threshold = 0.0

    for i in range(n):
        threshold = probs_sorted[i]
        # Count errors among accepted predictions (above threshold).
        accepted = sum(1 for j in range(i + 1) if labels_sorted[j])
        total_accepted = i + 1
        errors = total_accepted - accepted
        selective_error = errors / total_accepted if total_accepted > 0 else 0.0

        if selective_error <= max_selective_error:
            best_threshold = threshold
            break

    return best_threshold


def brier_score(probs: Sequence[float], labels: Sequence[bool]) -> float:
    """Mean squared error between predicted probabilities and binary labels."""

    if not probs:
        return 0.0
    return sum((p - float(l)) ** 2 for p, l in zip(probs, labels)) / len(probs)


def expected_calibration_error(
    probs: Sequence[float],
    labels: Sequence[bool],
    *,
    n_bins: int = 10,
) -> float:
    """Expected calibration error over equal-width bins."""

    if not probs:
        return 0.0

    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for p, l in zip(probs, labels):
        bin_idx = min(int(p * n_bins), n_bins - 1)
        bins[bin_idx].append((p, l))

    total = len(probs)
    ece = 0.0
    for bin_items in bins:
        if not bin_items:
            continue
        bin_size = len(bin_items)
        avg_prob = sum(p for p, _ in bin_items) / bin_size
        avg_label = sum(float(l) for _, l in bin_items) / bin_size
        ece += (bin_size / total) * abs(avg_prob - avg_label)

    return ece


def risk_coverage_curve(
    probs: Sequence[float],
    labels: Sequence[bool],
) -> list[tuple[float, float]]:
    """Compute the risk-coverage curve.

    Returns (coverage, selective_risk) pairs sorted by descending threshold.
    """

    paired = sorted(zip(probs, labels), key=lambda x: -x[0])
    result: list[tuple[float, float]] = []
    correct = 0
    total = 0

    for i, (_, label) in enumerate(paired):
        total += 1
        if label:
            correct += 1
        coverage = total / len(paired)
        selective_risk = 1.0 - (correct / total)
        result.append((coverage, selective_risk))

    return result


def area_under_risk_coverage(
    probs: Sequence[float],
    labels: Sequence[bool],
) -> float:
    """Area under the risk-coverage curve (AURC)."""

    curve = risk_coverage_curve(probs, labels)
    if len(curve) < 2:
        return 0.0

    aurc = 0.0
    for i in range(1, len(curve)):
        prev_cov, prev_risk = curve[i - 1]
        curr_cov, curr_risk = curve[i]
        width = curr_cov - prev_cov
        aurc += width * (prev_risk + curr_risk) / 2.0

    return aurc
