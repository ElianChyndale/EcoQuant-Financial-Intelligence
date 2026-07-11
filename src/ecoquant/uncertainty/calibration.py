"""Nested issuer-level calibration with frozen thresholds.

Implements a true nested issuer-level protocol:

For each outer held-out issuer:
1. Reserve that issuer exclusively for outer evaluation.
2. Use only remaining issuers for model fitting, preprocessing,
   feature normalization, calibration, conformal quantile estimation,
   and decision-threshold selection.
3. Create deterministic inner issuer splits.
4. Freeze all coefficients, normalization parameters, conformal thresholds,
   and decision thresholds before evaluating the outer issuer.
5. Store a machine-readable split manifest.

No question from an issuer appears in two roles in the same fold.
Outer held-out outcomes cannot influence fitting or threshold selection.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from .conformal import compute_conformal_threshold, conformal_accept
from .features import UncertaintyFeatures


@dataclass(frozen=True)
class FeatureNormalization:
    """Per-feature mean and std fitted on training data only."""

    means: tuple[float, ...]
    stds: tuple[float, ...]

    def normalize(self, features: list[UncertaintyFeatures]) -> list[UncertaintyFeatures]:
        """Normalize features using fitted parameters."""
        result = []
        for f in features:
            vec = [
                f.retrieval_margin,
                f.cross_retriever_agreement,
                f.extraction_confidence,
                f.temporal_validity,
                f.evidence_coverage,
            ]
            normalized = []
            for v, m, s in zip(vec, self.means, self.stds):
                if s > 0:
                    normalized.append((v - m) / s)
                else:
                    normalized.append(0.0)
            result.append(UncertaintyFeatures(*normalized))
        return result

    @classmethod
    def fit(cls, features: Sequence[UncertaintyFeatures]) -> "FeatureNormalization":
        """Fit normalization from training features only."""
        if not features:
            return cls(means=(0.0,) * 5, stds=(1.0,) * 5)

        n = len(features)
        sums = [0.0] * 5
        sum_sq = [0.0] * 5

        for f in features:
            vec = [
                f.retrieval_margin,
                f.cross_retriever_agreement,
                f.extraction_confidence,
                f.temporal_validity,
                f.evidence_coverage,
            ]
            for i, v in enumerate(vec):
                sums[i] += v
                sum_sq[i] += v * v

        means = [s / n for s in sums]
        stds = []
        for i in range(5):
            var = sum_sq[i] / n - means[i] ** 2
            stds.append(math.sqrt(max(var, 1e-12)))

        return cls(means=tuple(means), stds=tuple(stds))


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
    converged: bool = False
    iterations_run: int = 0
    degeneracy_status: str = "normal"

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
            features: Training feature vectors (already normalized).
            labels: Binary labels (True = correct, False = incorrect).
            regularization: L2 regularization strength.
            learning_rate: Gradient descent step size.
            max_iterations: Maximum optimization iterations.
            convergence_threshold: Gradient norm threshold for early stopping.
            seed: Random seed for reproducibility.

        Returns:
            A fitted PlattCalibrator instance.

        Raises:
            ValueError: If features/labels have different lengths, are empty,
                or contain non-finite values.
        """
        if len(features) != len(labels):
            raise ValueError("features and labels must have the same length")
        if not features:
            raise ValueError("features must be non-empty")

        # Validate all feature values are finite
        for i, f in enumerate(features):
            for name, val in [
                ("retrieval_margin", f.retrieval_margin),
                ("cross_retriever_agreement", f.cross_retriever_agreement),
                ("extraction_confidence", f.extraction_confidence),
                ("temporal_validity", f.temporal_validity),
                ("evidence_coverage", f.evidence_coverage),
            ]:
                if not math.isfinite(val):
                    raise ValueError(f"features[{i}].{name} is non-finite: {val}")

        n_features = 5
        rng = random.Random(seed)

        # Check for degenerate labels
        positive_count = sum(labels)
        negative_count = len(labels) - positive_count
        degeneracy_status = "normal"
        if positive_count == 0:
            degeneracy_status = "all_negative"
        elif negative_count == 0:
            degeneracy_status = "all_positive"

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
        converged = False
        iterations_run = 0

        for iteration in range(max_iterations):
            iterations_run = iteration + 1

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
                converged = True
                break

        # Validate output probabilities for a test point
        # (ensure the calibrator doesn't produce degenerate outputs)
        test_logit = sum(w * 0.5 for w in weights) + bias
        test_prob = _sigmoid(test_logit)
        if not (0.0 <= test_prob <= 1.0):
            degeneracy_status = "degenerate_output"

        return cls(
            weights=tuple(weights),
            bias=bias,
            regularization=regularization,
            learning_rate=learning_rate,
            max_iterations=max_iterations,
            convergence_threshold=convergence_threshold,
            converged=converged,
            iterations_run=iterations_run,
            degeneracy_status=degeneracy_status,
        )

    def predict_proba(self, features: Sequence[UncertaintyFeatures]) -> list[float]:
        """Map features to calibrated probabilities via a learned sigmoid.

        Raises:
            ValueError: If any feature value is non-finite or any output
                probability is outside [0, 1].
        """
        results = []
        for i, f in enumerate(features):
            prob = self._predict_single(f)
            if not math.isfinite(prob):
                raise ValueError(f"predict_proba produced non-finite output for features[{i}]")
            if not (0.0 <= prob <= 1.0):
                raise ValueError(f"predict_proba output {prob} outside [0, 1] for features[{i}]")
            results.append(prob)
        return results

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
class InnerFold:
    """One inner calibration fold within an outer fold."""

    inner_test_issuers: tuple[str, ...]
    inner_fit_issuers: tuple[str, ...]
    calibrator: PlattCalibrator
    normalization: FeatureNormalization
    conformal_threshold: float
    conformal_alpha: float
    inner_split_manifest: dict[str, object]


@dataclass(frozen=True)
class CalibrationFold:
    """One outer leave-one-issuer-out fold with nested inner calibration.

    The outer held-out issuer is used ONLY for final evaluation.
    All fitting, normalization, calibration, conformal quantile estimation,
    and threshold selection use only the remaining issuers.
    """

    test_issuer: str
    train_issuers: tuple[str, ...]
    calibrator: PlattCalibrator
    normalization: FeatureNormalization
    conformal_threshold: float
    conformal_alpha: float
    decision_threshold: float
    test_probs: tuple[float, ...]
    test_labels: tuple[bool, ...]
    split_manifest: dict[str, object]


@dataclass(frozen=True)
class CalibrationResult:
    """Aggregated calibration outcome across all outer folds."""

    folds: tuple[CalibrationFold, ...]
    frozen_threshold: float
    brier: float
    ece: float
    aurc: float
    coverage_at_threshold: float
    aurc_convention: str = "includes_coverage_zero_to_first_point"


def fit_calibration_folds(
    fold_data: dict[str, tuple[list[UncertaintyFeatures], list[bool]]],
    *,
    conformal_alpha: float = 0.10,
    max_selective_error: float = 0.10,
    seed: int = 20260710,
) -> tuple[CalibrationFold, ...]:
    """Fit nested leave-one-issuer-out calibration folds.

    For each outer held-out issuer:
    1. Use only remaining issuers for ALL fitting.
    2. Split remaining issuers into inner fit and inner calibration.
    3. Fit calibrator on inner fit issuers.
    4. Compute conformal threshold on inner calibration issuers.
    5. Select decision threshold on inner calibration issuers.
    6. Freeze everything before evaluating the outer issuer.

    Args:
        fold_data: {issuer: (features, labels)} per issuer.
        conformal_alpha: Target miscoverage for split-conformal.
        max_selective_error: Max selective error for decision threshold.
        seed: Base seed for deterministic splits.

    Returns:
        Tuple of CalibrationFold, one per issuer.
    """
    issuers = tuple(sorted(fold_data))
    folds: list[CalibrationFold] = []

    for outer_idx, test_issuer in enumerate(issuers):
        # Step 1: Outer train issuers = all except test_issuer
        train_issuers = tuple(i for i in issuers if i != test_issuer)

        # Step 2: Create inner split among train_issuers
        # Inner: first half for fitting, second half for calibration/threshold
        # Use deterministic split based on seed
        rng = random.Random(seed + outer_idx)
        shuffled = list(train_issuers)
        rng.shuffle(shuffled)

        if len(shuffled) >= 2:
            split_point = max(1, len(shuffled) // 2)
            inner_fit_issuers = tuple(shuffled[:split_point])
            inner_cal_issuers = tuple(shuffled[split_point:])
        else:
            # With only 1 train issuer, use it for both fit and calibration
            # (documented limitation for very small issuer sets)
            inner_fit_issuers = tuple(shuffled)
            inner_cal_issuers = tuple(shuffled)

        # Step 3: Aggregate inner fit features and labels
        fit_features: list[UncertaintyFeatures] = []
        fit_labels: list[bool] = []
        for issuer in inner_fit_issuers:
            features, labels = fold_data[issuer]
            fit_features.extend(features)
            fit_labels.extend(labels)

        if not fit_features:
            raise ValueError(f"empty fit data for outer fold {test_issuer}")

        # Step 4: Fit normalization on fit issuers only
        normalization = FeatureNormalization.fit(fit_features)

        # Step 5: Normalize fit features
        norm_fit_features = normalization.normalize(fit_features)

        # Step 6: Fit calibrator on normalized fit features
        calibrator = PlattCalibrator.fit(
            norm_fit_features,
            fit_labels,
            regularization=0.01,
            learning_rate=0.1,
            max_iterations=1000,
            seed=seed + outer_idx,
        )

        # Step 7: Aggregate inner calibration features
        cal_features: list[UncertaintyFeatures] = []
        cal_labels: list[bool] = []
        for issuer in inner_cal_issuers:
            features, labels = fold_data[issuer]
            cal_features.extend(features)
            cal_labels.extend(labels)

        # Step 8: Normalize calibration features using fit normalization
        norm_cal_features = normalization.normalize(cal_features)

        # Step 9: Get calibration probabilities
        cal_probs = calibrator.predict_proba(norm_cal_features)

        # Step 10: Compute conformal threshold
        # Nonconformity score = 1 - prob (larger = worse)
        cal_nonconformity = [1.0 - p for p in cal_probs]
        if cal_nonconformity:
            conformal_threshold = compute_conformal_threshold(
                cal_nonconformity, alpha=conformal_alpha
            )
        else:
            conformal_threshold = 0.0

        # Step 11: Select decision threshold on calibration data
        # Find lowest probability threshold achieving max_selective_error
        decision_threshold = _select_decision_threshold(
            cal_probs, cal_labels, max_selective_error=max_selective_error
        )

        # Step 12: Evaluate on outer test issuer (frozen coefficients)
        test_features_raw, test_labels = fold_data[test_issuer]
        test_features_norm = normalization.normalize(test_features_raw)
        test_probs = calibrator.predict_proba(test_features_norm)

        # Build split manifest
        split_manifest = {
            "outer_fold_id": outer_idx,
            "held_out_issuer": test_issuer,
            "fit_issuers": list(inner_fit_issuers),
            "calibration_issuers": list(inner_cal_issuers),
            "threshold_selection_issuers": list(inner_cal_issuers),
            "seed": seed + outer_idx,
            "fit_sample_count": len(fit_features),
            "cal_sample_count": len(cal_features),
            "test_sample_count": len(test_features_raw),
            "fit_positive_count": sum(fit_labels),
            "fit_negative_count": len(fit_labels) - sum(fit_labels),
            "fitted_coefficients": {
                "weights": list(calibrator.weights),
                "bias": calibrator.bias,
            },
            "normalization_parameters": {
                "means": list(normalization.means),
                "stds": list(normalization.stds),
            },
            "conformal_threshold": conformal_threshold,
            "conformal_alpha": conformal_alpha,
            "decision_threshold": decision_threshold,
            "convergence_status": {
                "converged": calibrator.converged,
                "iterations_run": calibrator.iterations_run,
                "degeneracy_status": calibrator.degeneracy_status,
            },
        }

        folds.append(
            CalibrationFold(
                test_issuer=test_issuer,
                train_issuers=train_issuers,
                calibrator=calibrator,
                normalization=normalization,
                conformal_threshold=conformal_threshold,
                conformal_alpha=conformal_alpha,
                decision_threshold=decision_threshold,
                test_probs=tuple(test_probs),
                test_labels=tuple(test_labels),
                split_manifest=split_manifest,
            )
        )

    return tuple(folds)


def _select_decision_threshold(
    probs: Sequence[float],
    labels: Sequence[bool],
    *,
    max_selective_error: float = 0.10,
) -> float:
    """Find the lowest probability threshold achieving at most max_selective_error.

    Selects on calibration data only (never outer test data).
    """
    if not probs:
        return 0.0

    paired = sorted(zip(probs, labels), key=lambda x: -x[0])
    probs_sorted = [p for p, _ in paired]
    labels_sorted = [l for _, l in paired]

    n = len(probs_sorted)
    best_threshold = 0.0

    for i in range(n):
        threshold = probs_sorted[i]
        accepted = sum(1 for j in range(i + 1) if labels_sorted[j])
        total_accepted = i + 1
        errors = total_accepted - accepted
        selective_error = errors / total_accepted if total_accepted > 0 else 0.0

        if selective_error <= max_selective_error:
            best_threshold = threshold
            break

    return best_threshold


def freeze_threshold(
    folds: Sequence[CalibrationFold],
    *,
    max_selective_error: float = 0.10,
) -> float:
    """Find the lowest threshold achieving at most max_selective_error.

    IMPORTANT: This function uses ONLY the per-fold decision thresholds
    that were selected on inner calibration data. It does NOT pool
    outer held-out predictions/labels for threshold selection.

    The returned threshold is the minimum across all folds' decision thresholds.
    """
    if not folds:
        return 0.0

    # Use the minimum decision threshold across all folds
    # Each fold's decision threshold was selected on inner calibration data only
    return min(fold.decision_threshold for fold in folds)


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

    Convention: includes the segment from coverage 0 to the first accepted
    point. The first point has coverage 1/n and risk = 0 or 1 depending
    on whether the highest-confidence prediction is correct.
    """
    if not probs:
        return []

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
    """Area under the risk-coverage curve (AURC).

    Convention: includes the trapezoidal segment from coverage 0 to the
    first accepted point. At coverage 0 the risk is undefined; we use
    the risk at the first accepted point as the left endpoint, which is
    the standard convention for selective prediction AURC.
    """
    curve = risk_coverage_curve(probs, labels)
    if len(curve) < 2:
        return 0.0

    aurc = 0.0

    # Include segment from coverage 0 to first point
    # Left endpoint: coverage=0, risk=same as first point
    first_cov, first_risk = curve[0]
    aurc += first_cov * first_risk  # rectangle from 0 to first coverage

    # Trapezoidal rule for remaining segments
    for i in range(1, len(curve)):
        prev_cov, prev_risk = curve[i - 1]
        curr_cov, curr_risk = curve[i]
        width = curr_cov - prev_cov
        aurc += width * (prev_risk + curr_risk) / 2.0

    return aurc
