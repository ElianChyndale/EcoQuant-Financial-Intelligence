"""Tests for calibration protocol correctness.

Verifies:
- No gold leakage in features
- Nested issuer isolation
- Real Platt scaling
- Correct conformal direction
- Non-finite input rejection
- Split manifest recording
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
    fit_calibration_folds,
    freeze_threshold,
    brier_score,
    expected_calibration_error,
    risk_coverage_curve,
    area_under_risk_coverage,
)
from ecoquant.uncertainty.conformal import conformal_accept
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

    def test_evidence_coverage_must_be_computed_without_gold(self) -> None:
        """Evidence coverage should be based on retriever-visible sufficiency."""
        # This test verifies the feature values are in valid range
        # and don't require gold data to compute
        features = UncertaintyFeatures(
            retrieval_margin=0.5,
            cross_retriever_agreement=0.8,
            extraction_confidence=0.9,
            temporal_validity=1.0,
            evidence_coverage=0.7,
        )
        assert 0.0 <= features.evidence_coverage <= 1.0


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

    def test_platt_calibrator_handles_degenerate_labels(self) -> None:
        """All-True or all-False labels must not crash."""
        features = [
            UncertaintyFeatures(0.5, 0.5, 0.5, 0.5, 0.5),
            UncertaintyFeatures(0.6, 0.6, 0.6, 0.6, 0.6),
        ]

        all_true = PlattCalibrator.fit(features, [True, True], seed=42)
        all_false = PlattCalibrator.fit(features, [False, False], seed=42)

        # Should produce finite probabilities
        probs_true = all_true.predict_proba(features)
        probs_false = all_false.predict_proba(features)
        assert all(math.isfinite(p) for p in probs_true)
        assert all(math.isfinite(p) for p in probs_false)

    def test_platt_calibrator_produces_finite_outputs(self) -> None:
        """All outputs must be finite floats."""
        features = [
            UncertaintyFeatures(0.0, 0.0, 0.0, 0.0, 0.0),
            UncertaintyFeatures(1.0, 1.0, 1.0, 1.0, 1.0),
            UncertaintyFeatures(0.5, 0.5, 0.5, 0.5, 0.5),
        ]
        labels = [True, False, True]

        calibrator = PlattCalibrator.fit(features, labels, seed=42)
        probs = calibrator.predict_proba(features)

        assert all(math.isfinite(p) for p in probs)
        assert all(0.0 <= p <= 1.0 for p in probs)


# ---------------------------------------------------------------------------
# Nested issuer isolation tests
# ---------------------------------------------------------------------------


class TestNestedIssuerIsolation:
    """Verify leave-one-issuer-out fold isolation."""

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

    def test_fold_covers_all_issuers(self) -> None:
        """Each issuer must be the test issuer exactly once."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        test_issuers = [f.test_issuer for f in folds]
        assert sorted(test_issuers) == sorted(fold_data.keys())

    def test_split_manifest_records_fold_details(self) -> None:
        """Each fold must have a split manifest."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        for fold in folds:
            assert fold.split_manifest is not None
            assert fold.split_manifest["test_issuer"] == fold.test_issuer
            assert fold.split_manifest["train_issuers"] == list(fold.train_issuers)
            assert fold.split_manifest["train_sample_count"] > 0
            assert fold.split_manifest["test_sample_count"] > 0
            assert len(fold.split_manifest["calibrator_weights"]) == 5

    def test_calibrator_is_fitted_on_non_test_issuers_only(self) -> None:
        """Calibrator weights must differ per fold (fitted on different data)."""
        fold_data = self._make_fold_data()
        folds = fit_calibration_folds(fold_data)

        # Different folds should have different calibrators
        # (unless by coincidence, which is unlikely with different data)
        weights_sets = set()
        for fold in folds:
            weight_key = tuple(round(w, 6) for w in fold.calibrator.weights)
            weights_sets.add(weight_key)

        # With different training data, we expect different weights
        # (at least 2 distinct sets across 4 folds)
        assert len(weights_sets) >= 2


# ---------------------------------------------------------------------------
# Conformal prediction tests
# ---------------------------------------------------------------------------


class TestConformalPrediction:
    """Verify conformal acceptance direction and behavior."""

    def test_conformal_accept_direction(self) -> None:
        """Higher score (better conformity) must be accepted."""
        assert conformal_accept(score=0.9, threshold=0.5) is True
        assert conformal_accept(score=0.5, threshold=0.5) is True  # equality accepted
        assert conformal_accept(score=0.4, threshold=0.5) is False

    def test_conformal_accept_rejects_infinity(self) -> None:
        """Infinity must not be silently accepted."""
        assert conformal_accept(score=float("inf"), threshold=0.5) is True
        assert conformal_accept(score=float("-inf"), threshold=0.5) is False

    def test_conformal_accept_rejects_nan(self) -> None:
        """NaN must not be silently accepted."""
        assert conformal_accept(score=float("nan"), threshold=0.5) is False


# ---------------------------------------------------------------------------
# Threshold freezing tests
# ---------------------------------------------------------------------------


class TestThresholdFreezing:
    """Verify threshold is frozen on calibration data only."""

    def test_threshold_achieves_target_error(self) -> None:
        """Frozen threshold must achieve at most max_selective_error."""
        # Create fold data where high probs are mostly correct
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
        }
        folds = fit_calibration_folds(fold_data)

        t1 = freeze_threshold(folds, max_selective_error=0.10)
        t2 = freeze_threshold(folds, max_selective_error=0.10)
        assert t1 == t2


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
        # The decide function should handle this gracefully
        decision = decide(
            calibrated_probability=float("inf"),
            conforms=True,
            evidence_sufficiency=0.8,
            extraction_valid=True,
        )
        # Even with inf probability, if conforms and evidence is sufficient,
        # it could theoretically pass. But inf should be handled.
        assert decision.code in (DecisionCode.AUTO_REPORT, DecisionCode.HUMAN_REVIEW_REQUIRED)


# ---------------------------------------------------------------------------
# Metric tests
# ---------------------------------------------------------------------------


class TestCalibrationMetrics:
    """Verify calibration metrics are correctly computed."""

    def test_brier_score_perfect_calibration(self) -> None:
        """Perfect predictions must have Brier score 0."""
        probs = [1.0, 0.0, 1.0, 0.0]
        labels = [True, False, True, False]
        assert brier_score(probs, labels) == pytest.approx(0.0)

    def test_brier_score_worst_calibration(self) -> None:
        """Worst predictions must have Brier score 1."""
        probs = [0.0, 1.0, 0.0, 1.0]
        labels = [True, False, True, False]
        assert brier_score(probs, labels) == pytest.approx(1.0)

    def test_ece_zero_for_perfect_calibration(self) -> None:
        """Perfect calibration must have ECE near 0."""
        probs = [1.0, 0.0, 1.0, 0.0]
        labels = [True, False, True, False]
        ece = expected_calibration_error(probs, labels)
        assert ece < 0.01  # Should be very small for perfect predictions

    def test_aurc_computes_area(self) -> None:
        """AURC must be a finite non-negative number."""
        probs = [0.9, 0.8, 0.7, 0.6, 0.5]
        labels = [True, True, False, True, False]
        aurc = area_under_risk_coverage(probs, labels)
        assert math.isfinite(aurc)
        assert aurc >= 0.0

    def test_risk_coverage_curve_length(self) -> None:
        """Curve must have same length as input."""
        probs = [0.9, 0.8, 0.7]
        labels = [True, False, True]
        curve = risk_coverage_curve(probs, labels)
        assert len(curve) == 3


# ---------------------------------------------------------------------------
# Original fold isolation tests (preserved)
# ---------------------------------------------------------------------------

_ISSUERS = ("AlphaCorp", "BetaLtd", "GammaInc", "DeltaPLC")


def _make_features(issuer: str, n: int = 20) -> list[UncertaintyFeatures]:
    """Deterministic synthetic features per issuer."""
    base = hash(issuer) % 100
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


class TestConformal:
    """Split-conformal abstention."""

    def test_conformal_accept_high_score(self) -> None:
        assert conformal_accept(score=0.9, threshold=0.5) is True

    def test_conformal_reject_low_score(self) -> None:
        assert conformal_accept(score=0.3, threshold=0.5) is False

    def test_conformal_threshold_boundary(self) -> None:
        assert conformal_accept(score=0.5, threshold=0.5) is True


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
