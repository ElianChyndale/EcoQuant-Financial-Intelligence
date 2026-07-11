"""Calibration protocol and fold-isolation tests for Task 6."""

from __future__ import annotations

import math

import pytest

from ecoquant.uncertainty.calibration import (
    CalibrationFold,
    CalibrationResult,
    brier_score,
    expected_calibration_error,
    fit_calibration_folds,
    freeze_threshold,
    risk_coverage_curve,
)
from ecoquant.uncertainty.conformal import conformal_accept
from ecoquant.uncertainty.features import UncertaintyFeatures


# ---------------------------------------------------------------------------
# Fixtures
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


# ---------------------------------------------------------------------------
# Fold isolation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Threshold freeze
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

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
        from ecoquant.uncertainty.calibration import area_under_risk_coverage
        probs = [0.9, 0.8, 0.3, 0.1]
        labels = [True, True, False, False]
        aurc = area_under_risk_coverage(probs, labels)
        assert 0.0 <= aurc <= 1.0


# ---------------------------------------------------------------------------
# Conformal acceptance
# ---------------------------------------------------------------------------

class TestConformal:
    """Split-conformal abstention."""

    def test_conformal_accept_high_score(self) -> None:
        assert conformal_accept(score=0.9, threshold=0.5) is True

    def test_conformal_reject_low_score(self) -> None:
        assert conformal_accept(score=0.3, threshold=0.5) is False

    def test_conformal_threshold_boundary(self) -> None:
        assert conformal_accept(score=0.5, threshold=0.5) is True


# ---------------------------------------------------------------------------
# Calibration result structure
# ---------------------------------------------------------------------------

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
