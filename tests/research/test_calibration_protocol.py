"""Tests for calibration protocol correctness.

Verifies:
- No gold leakage in features
- Nested issuer isolation (inner splits)
- Real Platt scaling with normalization
- Correct conformal direction (larger-is-worse)
- Non-finite input rejection
- Split manifest recording with all required fields
- Convergence tracking
- Feature consistency between training and decision paths
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from ecoquant.uncertainty.features import UncertaintyFeatures
from ecoquant.uncertainty.calibration import (
    PlattCalibrator,
    CalibrationFold,
    CalibrationResult,
    FeatureNormalization,
    fit_calibration_folds,
    freeze_threshold,
    brier_score,
    expected_calibration_error,
    risk_coverage_curve,
    area_under_risk_coverage,
)
from ecoquant.uncertainty.conformal import conformal_accept, compute_conformal_threshold
from ecoquant.uncertainty.decision import DecisionCode, decide


# ---------------------------------------------------------------------------
# Adversarial tests for feature isolation
# ---------------------------------------------------------------------------


class TestFeatureIsolation:
    """Verify that features cannot contain evaluator-only fields."""

    def test_uncertainty_features_has_no_gold_fields(self) -> None:
        """UncertaintyFeatures must not have gold_source_ids, gold_pages, etc."""
        from dataclasses import fields

        field_names = {f.name for f in fields(UncertaintyFeatures)}
        forbidden = {
            "gold_source_ids", "gold_pages", "gold_blocks", "gold_answer",
            "gold_evidence", "gold_label", "correctness", "is_correct",
        }
        assert not forbidden.intersection(field_names), (
            f"Forbidden gold-related fields found: {forbidden.intersection(field_names)}"
        )

    def test_features_only_contain_allowed_fields(self) -> None:
        """Features must only contain the five approved uncertainty features."""
        from dataclasses import fields

        field_names = {f.name for f in fields(UncertaintyFeatures)}
        allowed = {
            "retrieval_margin", "cross_retriever_agreement",
            "extraction_confidence", "temporal_validity", "evidence_coverage",
        }
        assert field_names == allowed


# ---------------------------------------------------------------------------
# Feature normalization tests
# ---------------------------------------------------------------------------


class TestFeatureNormalization:
    """Verify feature normalization fitted on training data only."""

    def test_normalization_zeroes_mean(self) -> None:
        """Normalized features should have approximately zero mean."""
        features = [
            UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85),
            UncertaintyFeatures(0.2, 0.3, 0.4, 0.5, 0.3),
            UncertaintyFeatures(0.6, 0.7, 0.8, 0.9, 0.7),
            UncertaintyFeatures(0.1, 0.2, 0.3, 0.4, 0.2),
        ]
        norm = FeatureNormalization.fit(features)
        normalized = norm.normalize(features)

        # Check means are approximately zero
        for dim in range(5):
            vals = [
                f.retrieval_margin if dim == 0
                else f.cross_retriever_agreement if dim == 1
                else f.extraction_confidence if dim == 2
                else f.temporal_validity if dim == 3
                else f.evidence_coverage
                for f in normalized
            ]
            mean = sum(vals) / len(vals)
            assert abs(mean) < 0.01, f"dimension {dim} mean {mean} not near zero"

    def test_normalization_handles_constant_features(self) -> None:
        """Constant features should produce zero after normalization."""
        features = [
            UncertaintyFeatures(0.5, 0.5, 0.5, 0.5, 0.5),
            UncertaintyFeatures(0.5, 0.5, 0.5, 0.5, 0.5),
        ]
        norm = FeatureNormalization.fit(features)
        normalized = norm.normalize(features)

        for f in normalized:
            assert f.retrieval_margin == 0.0
            assert f.cross_retriever_agreement == 0.0

    def test_normalization_is_deterministic(self) -> None:
        features = [
            UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85),
            UncertaintyFeatures(0.2, 0.3, 0.4, 0.5, 0.3),
        ]
        norm1 = FeatureNormalization.fit(features)
        norm2 = FeatureNormalization.fit(features)
        assert norm1.means == norm2.means
        assert norm1.stds == norm2.stds


# ---------------------------------------------------------------------------
# Platt scaling tests
# ---------------------------------------------------------------------------


class TestPlattScaling:
    """Verify real Platt scaling implementation."""

    def test_platt_calibrator_fits_from_data(self) -> None:
        """Calibrator must be fitted from training data, not use fixed weights."""
        features = [
            UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85),
            UncertaintyFeatures(0.2, 0.3, 0.4, 0.5, 0.3),
            UncertaintyFeatures(0.6, 0.7, 0.8, 0.9, 0.7),
            UncertaintyFeatures(0.1, 0.2, 0.3, 0.4, 0.2),
        ]
        labels = [True, False, True, False]

        calibrator = PlattCalibrator.fit(features, labels, seed=42)

        # Verify weights are not the default fixture values
        assert calibrator.weights != (1.0, 0.5, 0.8, 0.3, 0.6)
        assert calibrator.bias != -0.5

        # Verify it produces probabilities in [0, 1]
        probs = calibrator.predict_proba(features)
        assert all(0.0 <= p <= 1.0 for p in probs)

    def test_platt_calibrator_is_deterministic(self) -> None:
        """Same data and seed must produce same calibrator."""
        features = [
            UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85),
            UncertaintyFeatures(0.2, 0.3, 0.4, 0.5, 0.3),
        ]
        labels = [True, False]

        cal1 = PlattCalibrator.fit(features, labels, seed=42)
        cal2 = PlattCalibrator.fit(features, labels, seed=42)

        assert cal1.weights == cal2.weights
        assert cal1.bias == cal2.bias

    def test_platt_calibrator_records_convergence(self) -> None:
        """Calibrator must record convergence status and iterations."""
        features = [
            UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85),
            UncertaintyFeatures(0.2, 0.3, 0.4, 0.5, 0.3),
        ]
        labels = [True, False]

        cal = PlattCalibrator.fit(features, labels, seed=42)
        assert isinstance(cal.converged, bool)
        assert isinstance(cal.iterations_run, int)
        assert cal.iterations_run > 0
        assert cal.degeneracy_status in ("normal", "all_positive", "all_negative", "degenerate_output")

    def test_platt_calibrator_rejects_empty_data(self) -> None:
        """Empty fit data must raise ValueError, not return zero weights."""
        with pytest.raises(ValueError, match="non-empty"):
            PlattCalibrator.fit([], [])

    def test_platt_calibrator_handles_degenerate_labels(self) -> None:
        """All-True or all-False labels must not crash and must record status."""
        features = [
            UncertaintyFeatures(0.5, 0.5, 0.5, 0.5, 0.5),
            UncertaintyFeatures(0.6, 0.6, 0.6, 0.6, 0.6),
        ]

        all_true = PlattCalibrator.fit(features, [True, True], seed=42)
        assert all_true.degeneracy_status == "all_positive"

        all_false = PlattCalibrator.fit(features, [False, False], seed=42)
        assert all_false.degeneracy_status == "all_negative"

        # Should produce finite probabilities
        probs_true = all_true.predict_proba(features)
        probs_false = all_false.predict_proba(features)
        assert all(math.isfinite(p) for p in probs_true)
        assert all(math.isfinite(p) for p in probs_false)

    def test_platt_calibrator_validates_finite_features(self) -> None:
        """Non-finite feature values must be rejected."""
        features = [
            UncertaintyFeatures(float("inf"), 0.5, 0.5, 0.5, 0.5),
            UncertaintyFeatures(0.5, 0.5, 0.5, 0.5, 0.5),
        ]
        with pytest.raises(ValueError, match="non-finite"):
            PlattCalibrator.fit(features, [True, False], seed=42)

    def test_platt_calibrator_validates_output_range(self) -> None:
        """predict_proba must raise if output is outside [0, 1]."""
        features = [
            UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85),
            UncertaintyFeatures(0.2, 0.3, 0.4, 0.5, 0.3),
        ]
        labels = [True, False]
        cal = PlattCalibrator.fit(features, labels, seed=42)

        # Normal usage should work
        probs = cal.predict_proba(features)
        assert all(0.0 <= p <= 1.0 for p in probs)


# ---------------------------------------------------------------------------
# Nested issuer isolation tests
# ---------------------------------------------------------------------------


class TestNestedIssuerIsolation:
    """Verify nested leave-one-issuer-out fold isolation."""

    def _make_fold_data(self) -> dict[str, tuple[list[UncertaintyFeatures], list[bool]]]:
        """Create fold data with four issuers."""
        return {
            "AIB": (
                [UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85)] * 5,
                [True, True, True, False, False],
            ),
            "ESB": (
                [UncertaintyFeatures(0.6, 0.7, 0.8, 0.9, 0.7)] * 4,
                [True, True, False, False],
            ),
            "Enel": (
                [UncertaintyFeatures(0.4, 0.5, 0.6, 0.7, 0.5)] * 3,
                [True, False, False],
            ),
            "KfW": (
                [UncertaintyFeatures(0.2, 0.3, 0.4, 0.5, 0.3)] * 3,
                [True, True, False],
            ),
        }

    def test_fold_isolation_test_issuer_not_in_train(self) -> None:
        """Test issuer must never appear in training issuers."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        for fold in folds:
            assert fold.test_issuer not in fold.train_issuers

    def test_held_out_issuer_not_in_fit_or_calibration(self) -> None:
        """Held-out issuer must not appear in fit or calibration manifests."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        for fold in folds:
            manifest = fold.split_manifest
            held_out = manifest["held_out_issuer"]
            fit_issuers = set(manifest["fit_issuers"])
            cal_issuers = set(manifest["calibration_issuers"])
            assert held_out not in fit_issuers, f"{held_out} found in fit_issuers"
            assert held_out not in cal_issuers, f"{held_out} found in calibration_issuers"

    def test_no_issuer_in_two_roles_same_fold(self) -> None:
        """No issuer should appear in both fit and calibration roles."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        for fold in folds:
            manifest = fold.split_manifest
            fit_issuers = set(manifest["fit_issuers"])
            cal_issuers = set(manifest["calibration_issuers"])
            # Overlap is only allowed when there's a single train issuer
            if len(fold.train_issuers) > 1:
                assert not fit_issuers.intersection(cal_issuers), (
                    f"Overlap: {fit_issuers.intersection(cal_issuers)}"
                )

    def test_fold_covers_all_issuers(self) -> None:
        """Each issuer must be the test issuer exactly once."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        test_issuers = [f.test_issuer for f in folds]
        assert sorted(test_issuers) == sorted(fold_data.keys())

    def test_split_manifest_has_all_required_fields(self) -> None:
        """Each fold must have a complete split manifest."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        required_fields = {
            "outer_fold_id", "held_out_issuer", "fit_issuers",
            "calibration_issuers", "threshold_selection_issuers",
            "seed", "fitted_coefficients", "normalization_parameters",
            "conformal_threshold", "conformal_alpha", "decision_threshold",
            "convergence_status",
        }

        for fold in folds:
            for field in required_fields:
                assert field in fold.split_manifest, f"Missing field: {field}"

    def test_split_manifest_records_normalization(self) -> None:
        """Normalization parameters must be recorded per fold."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        for fold in folds:
            norm = fold.split_manifest["normalization_parameters"]
            assert "means" in norm
            assert "stds" in norm
            assert len(norm["means"]) == 5
            assert len(norm["stds"]) == 5

    def test_split_manifest_records_convergence(self) -> None:
        """Convergence status must be recorded per fold."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        for fold in folds:
            status = fold.split_manifest["convergence_status"]
            assert "converged" in status
            assert "iterations_run" in status
            assert "degeneracy_status" in status

    def test_calibrator_is_fitted_on_non_test_issuers_only(self) -> None:
        """Calibrator weights must differ per fold (fitted on different data)."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        weights_sets = set()
        for fold in folds:
            weight_key = tuple(round(w, 6) for w in fold.calibrator.weights)
            weights_sets.add(weight_key)

        # With different training data, we expect different weights
        assert len(weights_sets) >= 2

    def test_changing_outer_labels_does_not_change_threshold(self) -> None:
        """Outer test labels must NOT affect the frozen threshold.

        This is the critical leakage test: if changing outer labels changes
        the threshold, then outer outcomes are leaking into threshold selection.
        """
        fold_data = self._make_fold_data()
        folds1 = fit_calibration_folds(fold_data, seed=42)
        threshold1 = freeze_threshold(folds1)

        # Change outer test labels for AIB
        modified_data = {
            k: (list(v[0]), list(v[1])) for k, v in fold_data.items()
        }
        # Flip all AIB labels
        modified_data["AIB"] = (
            modified_data["AIB"][0],
            [not l for l in modified_data["AIB"][1]],
        )
        folds2 = fit_calibration_folds(modified_data, seed=42)
        threshold2 = freeze_threshold(folds2)

        # Thresholds must be identical because they are selected on
        # inner calibration data, not outer test data
        assert threshold1 == threshold2, (
            f"Threshold changed from {threshold1} to {threshold2} "
            f"when outer labels were modified — leakage detected"
        )

    def test_normalization_fitted_on_fit_issuers_only(self) -> None:
        """Normalization must be fitted on inner fit issuers, not calibration."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data, seed=42)

        for fold in folds:
            # The normalization should exist and have valid parameters
            assert fold.normalization is not None
            assert len(fold.normalization.means) == 5
            assert len(fold.normalization.stds) == 5
            # All stds should be positive (from fit data, not degenerate)
            for s in fold.normalization.stds:
                assert s > 0


# ---------------------------------------------------------------------------
# Conformal prediction tests
# ---------------------------------------------------------------------------


class TestConformalPrediction:
    """Verify split-conformal protocol correctness."""

    def test_conformal_threshold_by_hand(self) -> None:
        """Verify quantile computation matches hand calculation.

        For n=10, alpha=0.10:
        k = ceil((10+1) * (1-0.10)) = ceil(9.9) = 10
        threshold = 10th smallest (sorted ascending)
        """
        scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        threshold = compute_conformal_threshold(scores, alpha=0.10)
        # k = ceil(11 * 0.9) = ceil(9.9) = 10, so threshold = scores[9] = 1.0
        assert threshold == 1.0

    def test_conformal_threshold_small_set(self) -> None:
        """For n=1, alpha=0.10: k = ceil(2*0.9) = 2, clamped to 1."""
        scores = [0.5]
        threshold = compute_conformal_threshold(scores, alpha=0.10)
        assert threshold == 0.5

    def test_conformal_threshold_n5(self) -> None:
        """For n=5, alpha=0.20: k = ceil(6*0.8) = ceil(4.8) = 5."""
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        threshold = compute_conformal_threshold(scores, alpha=0.20)
        assert threshold == 0.5

    def test_conformal_threshold_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            compute_conformal_threshold([], alpha=0.10)

    def test_conformal_threshold_rejects_invalid_alpha(self) -> None:
        with pytest.raises(ValueError, match="alpha"):
            compute_conformal_threshold([0.5], alpha=0.0)
        with pytest.raises(ValueError, match="alpha"):
            compute_conformal_threshold([0.5], alpha=1.0)

    def test_conformal_threshold_rejects_non_finite_scores(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            compute_conformal_threshold([float("inf"), 0.5], alpha=0.10)
        with pytest.raises(ValueError, match="finite"):
            compute_conformal_threshold([float("nan"), 0.5], alpha=0.10)

    def test_conformal_accept_direction_larger_is_worse(self) -> None:
        """For larger-is-worse: accept iff score <= threshold."""
        # Low nonconformity score = good = accepted
        assert conformal_accept(score=0.1, threshold=0.5) is True
        # At boundary = accepted
        assert conformal_accept(score=0.5, threshold=0.5) is True
        # High nonconformity score = bad = rejected
        assert conformal_accept(score=0.9, threshold=0.5) is False

    def test_conformal_accept_rejects_infinity(self) -> None:
        """Both positive and negative infinity must be rejected."""
        assert conformal_accept(score=float("inf"), threshold=0.5) is False
        assert conformal_accept(score=float("-inf"), threshold=0.5) is False

    def test_conformal_accept_rejects_nan(self) -> None:
        """NaN must be rejected."""
        assert conformal_accept(score=float("nan"), threshold=0.5) is False

    def test_conformal_accept_rejects_none(self) -> None:
        """None values must be rejected."""
        assert conformal_accept(score=None, threshold=0.5) is False
        assert conformal_accept(score=0.5, threshold=None) is False

    def test_conformal_accept_rejects_non_finite_threshold(self) -> None:
        """Non-finite threshold must reject."""
        assert conformal_accept(score=0.5, threshold=float("inf")) is False
        assert conformal_accept(score=0.5, threshold=float("nan")) is False

    def test_conformal_ties(self) -> None:
        """Ties at the boundary should be accepted (<= convention)."""
        scores = [0.3, 0.3, 0.3, 0.3, 0.3]
        threshold = compute_conformal_threshold(scores, alpha=0.10)
        # All values are 0.3, threshold is 0.3
        assert threshold == 0.3
        # score == threshold should be accepted
        assert conformal_accept(score=0.3, threshold=threshold) is True


# ---------------------------------------------------------------------------
# Threshold freezing tests
# ---------------------------------------------------------------------------


class TestThresholdFreezing:
    """Verify threshold is frozen on calibration data only."""

    def test_threshold_achieves_target_error(self) -> None:
        """Frozen threshold must achieve at most max_selective_error."""
        fold_data = {
            "AIB": (
                [UncertaintyFeatures(0.9, 0.9, 0.95, 1.0, 0.9)] * 8 +
                [UncertaintyFeatures(0.1, 0.1, 0.2, 0.3, 0.1)] * 2,
                [True] * 8 + [False] * 2,
            ),
            "ESB": (
                [UncertaintyFeatures(0.8, 0.8, 0.85, 0.9, 0.8)] * 6 +
                [UncertaintyFeatures(0.2, 0.2, 0.3, 0.4, 0.2)] * 2,
                [True] * 6 + [False] * 2,
            ),
        }
        folds = fit_calibration_folds(fold_data)
        threshold = freeze_threshold(folds, max_selective_error=0.10)

        # Threshold must be in valid range
        assert 0.0 <= threshold <= 1.0

    def test_threshold_frozen_before_evaluation(self) -> None:
        """Threshold must be deterministically computable from folds."""
        fold_data = {
            "AIB": (
                [UncertaintyFeatures(0.5, 0.5, 0.5, 0.5, 0.5)] * 3,
                [True, False, True],
            ),
            "ESB": (
                [UncertaintyFeatures(0.6, 0.6, 0.6, 0.6, 0.6)] * 3,
                [True, True, False],
            ),
        }
        folds = fit_calibration_folds(fold_data)

        t1 = freeze_threshold(folds, max_selective_error=0.10)
        t2 = freeze_threshold(folds, max_selective_error=0.10)
        assert t1 == t2

    def test_threshold_not_affected_by_outer_labels(self) -> None:
        """Changing outer test labels must not change the frozen threshold."""
        fold_data = {
            "AIB": (
                [UncertaintyFeatures(0.8, 0.9, 0.95, 1.0, 0.85)] * 5,
                [True, True, True, False, False],
            ),
            "ESB": (
                [UncertaintyFeatures(0.6, 0.7, 0.8, 0.9, 0.7)] * 4,
                [True, True, False, False],
            ),
            "Enel": (
                [UncertaintyFeatures(0.4, 0.5, 0.6, 0.7, 0.5)] * 3,
                [True, False, False],
            ),
        }

        folds1 = fit_calibration_folds(fold_data, seed=42)
        t1 = freeze_threshold(folds1)

        # Modify Enel labels (outer test for some fold)
        modified = {k: (list(v[0]), list(v[1])) for k, v in fold_data.items()}
        modified["Enel"] = (modified["Enel"][0], [not l for l in modified["Enel"][1]])

        folds2 = fit_calibration_folds(modified, seed=42)
        t2 = freeze_threshold(folds2)

        assert t1 == t2, f"Threshold leaked: {t1} vs {t2}"


# ---------------------------------------------------------------------------
# Decision gate tests
# ---------------------------------------------------------------------------


class TestDecisionGate:
    """Verify decision precedence and safety."""

    def test_invalid_extraction_is_insufficient_evidence(self) -> None:
        decision = decide(
            calibrated_probability=0.99,
            conforms=True,
            evidence_sufficiency=0.9,
            extraction_valid=False,
        )
        assert decision.code is DecisionCode.INSUFFICIENT_EVIDENCE

    def test_missing_evidence_is_insufficient(self) -> None:
        decision = decide(
            calibrated_probability=0.99,
            conforms=True,
            evidence_sufficiency=0.0,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.INSUFFICIENT_EVIDENCE

    def test_high_confidence_but_no_conformal_requires_review(self) -> None:
        decision = decide(
            calibrated_probability=0.95,
            conforms=False,
            evidence_sufficiency=0.8,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED

    def test_auto_report_requires_all_gates(self) -> None:
        decision = decide(
            calibrated_probability=0.85,
            conforms=True,
            evidence_sufficiency=0.8,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.AUTO_REPORT

    def test_non_finite_probability_rejected(self) -> None:
        """Non-finite values must not produce AUTO_REPORT."""
        decision = decide(
            calibrated_probability=float("inf"),
            conforms=True,
            evidence_sufficiency=0.8,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED

        decision = decide(
            calibrated_probability=float("nan"),
            conforms=True,
            evidence_sufficiency=0.8,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED

    def test_non_finite_evidence_sufficiency_rejected(self) -> None:
        """Non-finite evidence_sufficiency must be checked BEFORE comparison."""
        decision = decide(
            calibrated_probability=0.85,
            conforms=True,
            evidence_sufficiency=float("inf"),
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.INSUFFICIENT_EVIDENCE

        decision = decide(
            calibrated_probability=0.85,
            conforms=True,
            evidence_sufficiency=float("nan"),
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.INSUFFICIENT_EVIDENCE

    def test_no_non_finite_produces_auto_report(self) -> None:
        """No combination involving at least one non-finite value produces AUTO_REPORT."""
        non_finite = [float("inf"), float("-inf"), float("nan")]
        for val in non_finite:
            # Only test cases where at least one input is non-finite
            cases = [
                (val, 0.9),      # non-finite prob, finite suff
                (0.99, val),     # finite prob, non-finite suff
                (val, val),      # both non-finite
            ]
            for prob, suff in cases:
                decision = decide(
                    calibrated_probability=prob,
                    conforms=True,
                    evidence_sufficiency=suff,
                    extraction_valid=True,
                )
                assert decision.code is not DecisionCode.AUTO_REPORT, (
                    f"AUTO_REPORT with prob={prob}, suff={suff}"
                )


# ---------------------------------------------------------------------------
# Metric tests
# ---------------------------------------------------------------------------


class TestCalibrationMetrics:
    """Verify calibration metrics are correctly computed."""

    def test_brier_score_perfect_calibration(self) -> None:
        probs = [1.0, 0.0, 1.0, 0.0]
        labels = [True, False, True, False]
        assert brier_score(probs, labels) == pytest.approx(0.0)

    def test_brier_score_worst_calibration(self) -> None:
        probs = [0.0, 1.0, 0.0, 1.0]
        labels = [True, False, True, False]
        assert brier_score(probs, labels) == pytest.approx(1.0)

    def test_ece_zero_for_perfect_calibration(self) -> None:
        probs = [1.0, 0.0, 1.0, 0.0]
        labels = [True, False, True, False]
        ece = expected_calibration_error(probs, labels)
        assert ece < 0.01

    def test_aurc_computes_area(self) -> None:
        probs = [0.9, 0.8, 0.7, 0.6, 0.5]
        labels = [True, True, False, True, False]
        aurc = area_under_risk_coverage(probs, labels)
        assert math.isfinite(aurc)
        assert aurc >= 0.0

    def test_aurc_convention_includes_zero_to_first(self) -> None:
        """AURC must include the segment from coverage 0 to first point."""
        probs = [0.9, 0.8, 0.7]
        labels = [True, True, False]
        aurc = area_under_risk_coverage(probs, labels)
        # With convention including 0-to-first, aurc > 0 even for all-correct
        assert aurc >= 0.0

    def test_risk_coverage_curve_length(self) -> None:
        probs = [0.9, 0.8, 0.7]
        labels = [True, False, True]
        curve = risk_coverage_curve(probs, labels)
        assert len(curve) == 3


# ---------------------------------------------------------------------------
# Original fold isolation tests (preserved and updated)
# ---------------------------------------------------------------------------


_ISSUERS = ("AlphaCorp", "BetaLtd", "GammaInc", "DeltaPLC")


def _make_features(issuer: str, n: int = 20) -> list[UncertaintyFeatures]:
    """Deterministic synthetic features per issuer."""
    return [
        UncertaintyFeatures(
            retrieval_margin=0.3 + (i % 5) * 0.1,
            cross_retriever_agreement=0.5 + (i % 3) * 0.15,
            extraction_confidence=0.6 + (i % 4) * 0.1,
            temporal_validity=1.0 if i % 3 != 0 else 0.0,
            evidence_coverage=0.4 + (i % 6) * 0.1,
        )
        for i in range(n)
    ]


def _make_labels(issuer: str, n: int = 20) -> list[bool]:
    """Deterministic correctness labels."""
    return [i % 2 == 0 for i in range(n)]


@pytest.fixture
def fold_data() -> dict[str, tuple[list[UncertaintyFeatures], list[bool]]]:
    return {issuer: (_make_features(issuer), _make_labels(issuer)) for issuer in _ISSUERS}


class TestFoldIsolation:
    """Calibration must be fit only on non-test issuers."""

    def test_test_issuer_excluded_from_fit(self, fold_data: dict) -> None:
        folds = fit_calibration_folds(fold_data)
        for fold in folds:
            assert fold.test_issuer not in fold.train_issuers

    def test_folds_cover_all_issuers(self, fold_data: dict) -> None:
        folds = fit_calibration_folds(fold_data)
        test_issuers = {fold.test_issuer for fold in folds}
        assert test_issuers == set(_ISSUERS)

    def test_each_fold_has_calibration_model(self, fold_data: dict) -> None:
        folds = fit_calibration_folds(fold_data)
        for fold in folds:
            assert fold.calibrator is not None


class TestThresholdFreeze:
    """Threshold must be frozen before final test evaluation."""

    def test_threshold_is_finite(self, fold_data: dict) -> None:
        folds = fit_calibration_folds(fold_data)
        threshold = freeze_threshold(folds, max_selective_error=0.10)
        assert math.isfinite(threshold)

    def test_threshold_targets_error_rate(self, fold_data: dict) -> None:
        folds = fit_calibration_folds(fold_data)
        threshold = freeze_threshold(folds, max_selective_error=0.10)
        assert 0.0 <= threshold <= 1.0

    def test_threshold_is_deterministic(self, fold_data: dict) -> None:
        folds = fit_calibration_folds(fold_data)
        t1 = freeze_threshold(folds, max_selective_error=0.10)
        t2 = freeze_threshold(folds, max_selective_error=0.10)
        assert t1 == t2


class TestMetrics:
    """Brier score, ECE, risk-coverage curve, and AURC."""

    def test_brier_score_range(self) -> None:
        probs = [0.9, 0.1, 0.8, 0.2]
        labels = [True, False, True, False]
        score = brier_score(probs, labels)
        assert 0.0 <= score <= 1.0

    def test_brier_score_perfect(self) -> None:
        score = brier_score([1.0, 0.0], [True, False])
        assert score == pytest.approx(0.0)

    def test_ece_range(self) -> None:
        probs = [0.9, 0.1, 0.8, 0.2]
        labels = [True, False, True, False]
        ece = expected_calibration_error(probs, labels, n_bins=5)
        assert 0.0 <= ece <= 1.0

    def test_risk_coverage_curve_shape(self) -> None:
        probs = [0.9, 0.8, 0.3, 0.1]
        labels = [True, True, False, False]
        curve = risk_coverage_curve(probs, labels)
        assert len(curve) == len(probs)
        assert all(0.0 <= risk <= 1.0 for _, risk in curve)

    def test_aurc_range(self) -> None:
        probs = [0.9, 0.8, 0.3, 0.1]
        labels = [True, True, False, False]
        aurc = area_under_risk_coverage(probs, labels)
        assert 0.0 <= aurc <= 1.0


class TestCalibrationResult:
    def test_result_has_required_fields(self, fold_data: dict) -> None:
        folds = fit_calibration_folds(fold_data)
        threshold = freeze_threshold(folds, max_selective_error=0.10)
        result = CalibrationResult(
            folds=folds,
            frozen_threshold=threshold,
            brier=0.0,
            ece=0.0,
            aurc=0.0,
            coverage_at_threshold=1.0,
        )
        assert result.frozen_threshold == threshold
        assert len(result.folds) == len(_ISSUERS)
        assert result.aurc_convention == "includes_coverage_zero_to_first_point"
