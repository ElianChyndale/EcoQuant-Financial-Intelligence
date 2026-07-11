"""Leave-one-issuer-out calibration with frozen thresholds.

All calibration is fit only on non-test issuers. The threshold is frozen
before final test evaluation to prevent leakage.

Implements real Platt scaling with gradient descent fitting.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from .features import UncertaintyFeatures


@dataclass(frozen=True)
class PlattCalibrator:
    """Platt-style calibrator fitted via gradient descent.

    Fits a logistic regression on the feature vector to produce calibrated
    probabilities. Uses L2 regularization for stability.
    """

    weights: tuple[float, ...]
    bias: float
    regularization: float = 0.01
    learning_rate: float = 0.1
    max_iterations: int = 1000
    convergence_threshold: float = 1e-6

    @classmethod
    def fit(
        cls,
        features: Sequence[UncertaintyFeatures],
        labels: Sequence[bool],
        *,
        regularization: float = 0.01,
        learning_rate: float = 0.1,
        max_iterations: int = 1000,
        convergence_threshold: float = 1e-6,
        seed: int = 20260710,
    ) -> "PlattCalibrator":
        """Fit a Platt calibrator from training data using gradient descent.

        Args:
            features: Training feature vectors.
            labels: Binary labels (True = correct, False = incorrect).
            regularization: L2 regularization strength.
            learning_rate: Gradient descent step size.
            max_iterations: Maximum optimization iterations.
            convergence_threshold: Gradient norm threshold for early stopping.
            seed: Random seed for reproducibility.

        Returns:
            A fitted PlattCalibrator instance.
        """
        if len(features) != len(labels):
            raise ValueError("features and labels must have the same length")
        if not features:
            return cls(weights=(0.0, 0.0, 0.0, 0.0, 0.0), bias=0.0)

        n_features = 5  # retrieval_margin, agreement, extraction, temporal, coverage
        rng = random.Random(seed)

        # Initialize weights with small random values
        weights = [rng.gauss(0, 0.1) for _ in range(n_features)]
        bias = 0.0

        # Convert features to arrays
        X = [
            [
                f.retrieval_margin,
                f.cross_retriever_agreement,
                f.extraction_confidence,
                f.temporal_validity,
                f.evidence_coverage,
            ]
            for f in features
        ]
        y = [1.0 if label else 0.0 for label in labels]

        # Gradient descent with L2 regularization
        for iteration in range(max_iterations):
            # Compute predictions
            predictions = []
            for x_i in X:
                logit = sum(w * x for w, x in zip(weights, x_i)) + bias
                pred = _sigmoid(logit)
                predictions.append(pred)

            # Compute gradients
            weight_gradients = [0.0] * n_features
            bias_gradient = 0.0

            for i in range(len(X)):
                error = predictions[i] - y[i]
                for j in range(n_features):
                    weight_gradients[j] += error * X[i][j]
                bias_gradient += error

            # Add L2 regularization
            for j in range(n_features):
                weight_gradients[j] += regularization * weights[j]

            # Average gradients
            n = len(X)
            for j in range(n_features):
                weight_gradients[j] /= n
            bias_gradient /= n

            # Update weights
            for j in range(n_features):
                weights[j] -= learning_rate * weight_gradients[j]
            bias -= learning_rate * bias_gradient

            # Check convergence
            gradient_norm = math.sqrt(
                sum(g ** 2 for g in weight_gradients) + bias_gradient ** 2
            )
            if gradient_norm < convergence_threshold:
                break

        return cls(
            weights=tuple(weights),
            bias=bias,
            regularization=regularization,
            learning_rate=learning_rate,
            max_iterations=max_iterations,
            convergence_threshold=convergence_threshold,
        )

    def predict_proba(self, features: Sequence[UncertaintyFeatures]) -> list[float]:
        """Map features to calibrated probabilities via a learned sigmoid."""
        return [self._predict_single(f) for f in features]

    def _predict_single(self, f: UncertaintyFeatures) -> float:
        logit = (
            self.weights[0] * f.retrieval_margin
            + self.weights[1] * f.cross_retriever_agreement
            + self.weights[2] * f.extraction_confidence
            + self.weights[3] * f.temporal_validity
            + self.weights[4] * f.evidence_coverage
            + self.bias
        )
        return _sigmoid(logit)


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid function."""
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
    calibrator: PlattCalibrator
    test_probs: tuple[float, ...]
    test_labels: tuple[bool, ...]
    split_manifest: dict[str, object]


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

        # Fit calibrator using real Platt scaling
        calibrator = PlattCalibrator.fit(
            train_features,
            train_labels,
            regularization=0.01,
            learning_rate=0.1,
            max_iterations=1000,
            seed=20260710,
        )

        # Evaluate on test issuer.
        test_features, test_labels = fold_data[test_issuer]
        test_probs = calibrator.predict_proba(test_features)

        # Record split manifest
        split_manifest = {
            "test_issuer": test_issuer,
            "train_issuers": list(train_issuers),
            "train_sample_count": len(train_features),
            "test_sample_count": len(test_features),
            "train_positive_count": sum(train_labels),
            "train_negative_count": len(train_labels) - sum(train_labels),
            "calibrator_weights": list(calibrator.weights),
            "calibrator_bias": calibrator.bias,
        }

        folds.append(
            CalibrationFold(
                test_issuer=test_issuer,
                train_issuers=train_issuers,
                calibrator=calibrator,
                test_probs=tuple(test_probs),
                test_labels=tuple(test_labels),
                split_manifest=split_manifest,
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

    Uses the conformal prediction approach:
    - Higher nonconformity score = worse conformity
    - Accept when score <= calibrated threshold
    """

    # Collect all calibration probabilities and labels.
    all_probs: list[float] = []
    all_labels: list[bool] = []
    for fold in folds:
        all_probs.extend(fold.test_probs)
        all_labels.extend(fold.test_labels)

    if not all_probs:
        return 0.0

    # Sort by probability descending (higher prob = more confident = better conformity)
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
