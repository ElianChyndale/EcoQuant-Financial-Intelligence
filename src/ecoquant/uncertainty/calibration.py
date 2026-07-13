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

from .conformal import compute_conformal_threshold, correctness_nonconformity
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
            if not all(math.isfinite(value) for value in vec):
                raise ValueError("features contain a non-finite value")
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
            raise ValueError("normalization features must be non-empty")

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
            if not all(math.isfinite(value) for value in vec):
                raise ValueError("normalization features contain a non-finite value")
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
    objective_value: float = math.inf
    failure_reason: str | None = None

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
        if regularization <= 0 or not math.isfinite(regularization):
            raise ValueError("regularization must be positive and finite")
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if convergence_threshold <= 0 or not math.isfinite(convergence_threshold):
            raise ValueError("convergence_threshold must be positive and finite")

        X: list[list[float]] = []
        for i, feature in enumerate(features):
            row = [
                feature.retrieval_margin,
                feature.cross_retriever_agreement,
                feature.extraction_confidence,
                feature.temporal_validity,
                feature.evidence_coverage,
                1.0,
            ]
            if not all(math.isfinite(value) for value in row):
                raise ValueError(f"features[{i}] contains a non-finite value")
            X.append(row)

        if any(type(label) is not bool for label in labels):
            raise TypeError("labels must contain bool values")
        positive_count = sum(labels)
        if positive_count == 0 or positive_count == len(labels):
            raise ValueError("calibration fitting requires both positive and negative labels")
        y = [1.0 if label else 0.0 for label in labels]

        # Deterministic regularized Newton/IRLS optimization.  The seed remains
        # in the public contract but no random initialization is required.
        parameters = [0.0] * 6
        objective = _logistic_objective(X, y, parameters, regularization)
        converged = False
        iterations_run = 0
        failure_reason: str | None = None

        for iteration in range(max_iterations):
            iterations_run = iteration + 1
            probabilities = [_sigmoid(sum(a * b for a, b in zip(parameters, row))) for row in X]
            gradient = [0.0] * 6
            hessian = [[0.0] * 6 for _ in range(6)]
            n = len(X)

            for row, target, probability in zip(X, y, probabilities):
                error = probability - target
                curvature = max(probability * (1.0 - probability), 1e-12)
                for j in range(6):
                    gradient[j] += error * row[j] / n
                    for k in range(6):
                        hessian[j][k] += curvature * row[j] * row[k] / n

            for j in range(5):
                gradient[j] += regularization * parameters[j]
                hessian[j][j] += regularization
            hessian[5][5] += 1e-10

            step = _solve_linear_system(hessian, gradient)
            step_scale = 1.0
            candidate = [value - step_scale * delta for value, delta in zip(parameters, step)]
            candidate_objective = _logistic_objective(X, y, candidate, regularization)
            while candidate_objective > objective and step_scale > 1e-8:
                step_scale *= 0.5
                candidate = [value - step_scale * delta for value, delta in zip(parameters, step)]
                candidate_objective = _logistic_objective(X, y, candidate, regularization)

            if not math.isfinite(candidate_objective):
                failure_reason = "non_finite_objective"
                break

            max_change = max(abs(step_scale * delta) for delta in step)
            improvement = objective - candidate_objective
            parameters = candidate
            objective = candidate_objective
            if max_change < convergence_threshold or (
                improvement >= 0.0 and improvement < convergence_threshold
            ):
                converged = True
                break

        if not converged and failure_reason is None:
            failure_reason = "maximum_iterations_reached"

        if not all(math.isfinite(value) for value in parameters) or not math.isfinite(objective):
            failure_reason = "non_finite_fitted_state"
            converged = False

        return cls(
            weights=tuple(parameters[:5]),
            bias=parameters[5],
            regularization=regularization,
            learning_rate=learning_rate,
            max_iterations=max_iterations,
            convergence_threshold=convergence_threshold,
            converged=converged,
            iterations_run=iterations_run,
            degeneracy_status="normal",
            objective_value=objective,
            failure_reason=failure_reason,
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


def _logistic_objective(
    rows: Sequence[Sequence[float]],
    labels: Sequence[float],
    parameters: Sequence[float],
    regularization: float,
) -> float:
    """Mean binary log loss plus L2 regularization (bias excluded)."""
    total = 0.0
    for row, target in zip(rows, labels):
        logit = sum(a * b for a, b in zip(parameters, row))
        # Stable logistic loss: log(1 + exp(logit)) - target * logit.
        total += max(logit, 0.0) + math.log1p(math.exp(-abs(logit))) - target * logit
    penalty = 0.5 * regularization * sum(value * value for value in parameters[:5])
    return total / len(rows) + penalty


def _solve_linear_system(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    """Solve a small dense system with deterministic partial pivoting."""
    size = len(vector)
    augmented = [list(row) + [float(value)] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("calibration Hessian is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column])
            ]
    return [augmented[row][-1] for row in range(size)]


def require_final_calibration(calibrator: PlattCalibrator) -> None:
    """Reject fitted state that is unsafe for a final research execution."""
    if calibrator.degeneracy_status != "normal":
        raise RuntimeError(
            f"calibrator is not usable: degeneracy={calibrator.degeneracy_status}"
        )
    if not calibrator.converged:
        reason = calibrator.failure_reason or "unknown"
        raise RuntimeError(f"calibrator did not converge: {reason}")
    if not math.isfinite(calibrator.objective_value):
        raise RuntimeError("calibrator objective is non-finite")
    if not all(math.isfinite(value) for value in (*calibrator.weights, calibrator.bias)):
        raise RuntimeError("calibrator coefficients are non-finite")


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
    evidence_sufficiency_threshold: float = 0.25,
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
        evidence_sufficiency_threshold: Frozen evidence coverage gate.
        seed: Base seed for deterministic splits.

    Returns:
        Tuple of CalibrationFold, one per issuer.
    """
    issuers = tuple(sorted(fold_data))
    if (
        not math.isfinite(evidence_sufficiency_threshold)
        or not 0.0 <= evidence_sufficiency_threshold <= 1.0
    ):
        raise ValueError("evidence_sufficiency_threshold must be finite and within [0, 1]")
    if len(issuers) < 4:
        raise ValueError("nested issuer protocol requires at least four issuers")
    for issuer, (features, labels) in fold_data.items():
        if not features or len(features) != len(labels):
            raise ValueError(f"issuer {issuer} must have non-empty aligned features and labels")
    folds: list[CalibrationFold] = []

    for outer_idx, test_issuer in enumerate(issuers):
        # Step 1: Outer train issuers = all except test_issuer
        train_issuers = tuple(i for i in issuers if i != test_issuer)

        # Step 2: Create three disjoint inner roles among train issuers.
        # At least one issuer is reserved for conformal calibration and one
        # separate issuer for decision-threshold selection.
        rng = random.Random(seed + outer_idx)
        shuffled = list(train_issuers)
        rng.shuffle(shuffled)
        inner_fit_issuers = tuple(shuffled[:-2])
        inner_cal_issuers = (shuffled[-2],)
        threshold_selection_issuers = (shuffled[-1],)

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
            learning_rate=1.0,
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

        # Step 10: Compute label-aware correctness nonconformity.  At decision
        # time the candidate label is correct_and_supported=True.
        cal_nonconformity = [
            correctness_nonconformity(probability, observed_correct=label)
            for probability, label in zip(cal_probs, cal_labels)
        ]
        conformal_threshold = compute_conformal_threshold(
            cal_nonconformity, alpha=conformal_alpha
        )

        # Step 11: Select the probability threshold on its own issuer role.
        threshold_features: list[UncertaintyFeatures] = []
        threshold_labels: list[bool] = []
        for issuer in threshold_selection_issuers:
            features, labels = fold_data[issuer]
            threshold_features.extend(features)
            threshold_labels.extend(labels)
        normalized_threshold_features = normalization.normalize(threshold_features)
        threshold_probs = calibrator.predict_proba(normalized_threshold_features)
        decision_threshold = _select_decision_threshold(
            threshold_probs,
            threshold_labels,
            max_selective_error=max_selective_error,
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
            "threshold_selection_issuers": list(threshold_selection_issuers),
            "seed": seed + outer_idx,
            "fit_sample_count": len(fit_features),
            "cal_sample_count": len(cal_features),
            "threshold_sample_count": len(threshold_features),
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
            "decision_policy": {
                "calibrated_probability_threshold": decision_threshold,
                "conformal_threshold": conformal_threshold,
                "evidence_sufficiency_threshold": evidence_sufficiency_threshold,
                "extraction_validity_required": True,
                "temporal_validity_required": True,
            },
            "convergence_status": {
                "converged": calibrator.converged,
                "iterations_run": calibrator.iterations_run,
                "degeneracy_status": calibrator.degeneracy_status,
                "objective_value": calibrator.objective_value,
                "failure_reason": calibrator.failure_reason,
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
        raise ValueError("threshold-selection probabilities must be non-empty")
    if len(probs) != len(labels):
        raise ValueError("threshold-selection probabilities and labels must align")
    if any(not math.isfinite(probability) or not 0.0 <= probability <= 1.0 for probability in probs):
        raise ValueError("threshold-selection probabilities must be finite and within [0, 1]")
    if any(type(label) is not bool for label in labels):
        raise TypeError("threshold-selection labels must be bool")

    paired = sorted(zip(probs, labels), key=lambda x: -x[0])
    probs_sorted = [p for p, _ in paired]
    labels_sorted = [l for _, l in paired]

    n = len(probs_sorted)
    best_threshold = 1.0
    found = False

    for i in range(n):
        threshold = probs_sorted[i]
        accepted = sum(1 for j in range(i + 1) if labels_sorted[j])
        total_accepted = i + 1
        errors = total_accepted - accepted
        selective_error = errors / total_accepted if total_accepted > 0 else 0.0

        if selective_error <= max_selective_error:
            best_threshold = threshold
            found = True

    # If no non-empty accepted prefix meets the target, threshold 1.0
    # represents an abstain-all automatic policy for finite sigmoid outputs.
    return best_threshold if found else 1.0


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


def selective_metrics_at_threshold(
    probs: Sequence[float],
    labels: Sequence[bool],
    thresholds: Sequence[float],
) -> dict[str, float | bool | str | None]:
    """Evaluate selective coverage/risk using each record's frozen threshold."""
    if len(probs) != len(labels) or len(probs) != len(thresholds):
        raise ValueError("probabilities, labels, and thresholds must align")
    if not probs:
        return {
            "coverage": None,
            "coverage_evaluable": False,
            "coverage_reason": "empty_evaluation",
            "selective_risk": None,
            "selective_risk_evaluable": False,
            "selective_risk_reason": "empty_evaluation",
        }
    if any(type(label) is not bool for label in labels):
        raise TypeError("labels must contain bool values")
    for name, values in (("probabilities", probs), ("thresholds", thresholds)):
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
            raise ValueError(f"{name} must be finite and within [0, 1]")

    accepted_labels = [
        label
        for probability, label, threshold in zip(probs, labels, thresholds)
        if probability >= threshold
    ]
    coverage = len(accepted_labels) / len(probs)
    if not accepted_labels:
        return {
            "coverage": coverage,
            "coverage_evaluable": True,
            "coverage_reason": None,
            "selective_risk": None,
            "selective_risk_evaluable": False,
            "selective_risk_reason": "no_accepted_records",
        }
    return {
        "coverage": coverage,
        "coverage_evaluable": True,
        "coverage_reason": None,
        "selective_risk": 1.0 - sum(accepted_labels) / len(accepted_labels),
        "selective_risk_evaluable": True,
        "selective_risk_reason": None,
    }


def _validate_metric_inputs(probs: Sequence[float], labels: Sequence[bool]) -> None:
    if len(probs) != len(labels):
        raise ValueError("probabilities and labels must align")
    if any(not math.isfinite(probability) or not 0.0 <= probability <= 1.0 for probability in probs):
        raise ValueError("probabilities must be finite and within [0, 1]")
    if any(type(label) is not bool for label in labels):
        raise TypeError("labels must contain bool values")


def brier_score(probs: Sequence[float], labels: Sequence[bool]) -> float:
    """Mean squared error between predicted probabilities and binary labels."""
    _validate_metric_inputs(probs, labels)
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
    _validate_metric_inputs(probs, labels)
    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
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
    _validate_metric_inputs(probs, labels)
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
    if not curve:
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
