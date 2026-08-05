from __future__ import annotations

import math

import pytest

from finvest.calibration.leak_free import (
    build_leak_free_features,
    evaluate_leak_free_calibration,
)
from finvest.calibration.robustness import (
    PERTURBATIONS,
    apply_perturbation,
    paired_effect,
)
from finvest.calibration.transfer import TransferResult, report_transfer
from ecoquant.uncertainty.features import UncertaintyFeatures


def test_build_leak_free_features_aligned() -> None:
    features = build_leak_free_features(
        margins=[0.5, 0.3], agreements=[1.0, 0.5],
        set_scores=[0.9, 0.6], temporal_flags=[1.0, 0.0],
        conflict_flags=[0.0, 1.0], execution_flags=[1.0, 1.0],
        entropies=[0.1, 0.8],
    )
    assert len(features) == 2
    assert features[0].top1_top2_margin == 0.5
    assert features[0].conflict_flag == 0.0


def test_leak_free_features_misaligned_raises() -> None:
    with pytest.raises(ValueError, match="aligned"):
        build_leak_free_features(
            margins=[0.5], agreements=[1.0, 0.5],
            set_scores=[0.9], temporal_flags=[1.0],
            conflict_flags=[0.0], execution_flags=[1.0], entropies=[0.1],
        )


def test_evaluate_leak_free_calibration_shape() -> None:
    # 4 issuers x 6 records (needs both classes per issuer for Platt).
    fold_data: dict[str, tuple[list, list]] = {}
    for issuer in ("A", "B", "C", "D"):
        features = [
            UncertaintyFeatures(0.9, 1.0, 0.9, 1.0, 0.0),
            UncertaintyFeatures(0.8, 1.0, 0.8, 1.0, 0.0),
            UncertaintyFeatures(0.7, 0.5, 0.7, 1.0, 0.0),
            UncertaintyFeatures(0.6, 0.5, 0.6, 0.0, 0.0),
            UncertaintyFeatures(0.5, 0.0, 0.5, 0.0, 0.0),
            UncertaintyFeatures(0.4, 0.0, 0.4, 0.0, 0.0),
        ]
        labels = [True, True, True, False, False, False]
        fold_data[issuer] = (features, labels)
    result = evaluate_leak_free_calibration(fold_data)
    assert "auroc" in result
    assert "auprc" in result
    assert "ece" in result
    assert "brier" in result
    assert 0.0 <= result["auroc"] <= 1.0
    assert 0.0 <= result["coverage_at_5pct_risk"] <= 1.0
    assert 0.0 <= result["risk_at_50pct_coverage"] <= 1.0


def test_all_perturbations_apply() -> None:
    base = ("Apple revenue was 391.0 billion in fiscal 2024 with notes.",)
    for perturbation in PERTURBATIONS:
        perturbed = apply_perturbation(
            base_case_id="c1", question="What is Apple revenue for FY2024?",
            evidence=base, perturbation=perturbation,
        )
        assert perturbed.base_case_id == "c1"
        assert perturbed.perturbation == perturbation
        assert isinstance(perturbed.question, str)


def test_paired_effect() -> None:
    assert paired_effect(0.8, 0.5) == pytest.approx(-0.3)  # degradation
    assert paired_effect(0.5, 0.8) == pytest.approx(0.3)


def test_transfer_report_no_merging() -> None:
    results = (
        TransferResult("finvest-train", "financebench", "all_required_recall", 0.6, 150),
        TransferResult("finvest-train", "griqa", "num_accuracy", 0.7, 266),
    )
    report = report_transfer(results)
    assert "finvest-train->financebench" in report
    assert "finvest-train->griqa" in report
    # Metrics not merged into a single average.
    assert report["finvest-train->financebench"]["all_required_recall"] == 0.6
    assert report["finvest-train->griqa"]["num_accuracy"] == 0.7
