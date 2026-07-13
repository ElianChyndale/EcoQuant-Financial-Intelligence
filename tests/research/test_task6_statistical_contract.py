"""Authoritative statistical contract tests for the Task 6 repair."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from ecoquant.retrieval.base import REGISTERED_METHOD_IDS, RetrievalResult
from ecoquant.retrieval.evaluation import EvaluatorGold
from ecoquant.uncertainty.calibration import (
    PlattCalibrator,
    area_under_risk_coverage,
    brier_score,
    expected_calibration_error,
    fit_calibration_folds,
    require_final_calibration,
    risk_coverage_curve,
    selective_metrics_at_threshold,
)
from ecoquant.uncertainty.conformal import (
    candidate_correctness_nonconformity,
    compute_conformal_threshold,
    conformal_accept,
    correctness_nonconformity,
)
from ecoquant.uncertainty.decision import DecisionCode, DecisionPolicy, decide
from ecoquant.uncertainty.features import UncertaintyFeatures
from scripts.run_research import (
    _build_features_for_question,
    _build_fold_data,
    _run_calibration,
    _run_decision_gating,
)


def _features(level: float, count: int = 8) -> list[UncertaintyFeatures]:
    return [
        UncertaintyFeatures(
            retrieval_margin=level + (index % 2) * 0.05,
            cross_retriever_agreement=0.5 + (index % 3) / 12,
            extraction_confidence=0.7 + (index % 2) * 0.1,
            temporal_validity=1.0,
            evidence_coverage=0.6 + (index % 2) * 0.1,
        )
        for index in range(count)
    ]


def _fold_data() -> dict[str, tuple[list[UncertaintyFeatures], list[bool]]]:
    return {
        "AIB": (_features(0.1), [True, False, True, False, True, False, True, False]),
        "ESB": (_features(0.3), [True, True, False, False, True, False, True, False]),
        "Enel": (_features(0.5), [False, True, False, True, True, False, True, False]),
        "KfW": (_features(0.7), [True, False, True, False, False, True, False, True]),
    }


def test_correctness_nonconformity_uses_observed_label() -> None:
    assert correctness_nonconformity(0.9, observed_correct=True) == pytest.approx(0.1)
    assert correctness_nonconformity(0.9, observed_correct=False) == pytest.approx(0.9)
    assert candidate_correctness_nonconformity(0.9) == pytest.approx(0.1)


def test_nested_roles_are_disjoint_and_threshold_has_its_own_issuer() -> None:
    folds = fit_calibration_folds(_fold_data(), seed=20260710)
    for fold in folds:
        manifest = fold.split_manifest
        roles = [
            set(manifest["fit_issuers"]),
            set(manifest["calibration_issuers"]),
            set(manifest["threshold_selection_issuers"]),
            {manifest["held_out_issuer"]},
        ]
        assert all(len(role) == 1 for role in roles)
        assert all(not left.intersection(right) for i, left in enumerate(roles) for right in roles[i + 1 :])


def _frozen_state_bytes(fold: object) -> bytes:
    manifest = fold.split_manifest  # type: ignore[attr-defined]
    keys = (
        "fit_issuers",
        "calibration_issuers",
        "threshold_selection_issuers",
        "fitted_coefficients",
        "normalization_parameters",
        "conformal_threshold",
        "conformal_alpha",
        "decision_threshold",
        "decision_policy",
        "convergence_status",
    )
    return json.dumps(
        {key: manifest[key] for key in keys},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_outer_label_mutation_leaves_frozen_state_byte_identical() -> None:
    original = fit_calibration_folds(_fold_data(), seed=20260710)
    changed = _fold_data()
    features, labels = changed["AIB"]
    changed["AIB"] = (features, [not value for value in labels])
    modified = fit_calibration_folds(changed, seed=20260710)

    before = next(fold for fold in original if fold.test_issuer == "AIB")
    after = next(fold for fold in modified if fold.test_issuer == "AIB")
    assert _frozen_state_bytes(before) == _frozen_state_bytes(after)


def test_outer_prediction_mutation_leaves_frozen_state_byte_identical() -> None:
    original = fit_calibration_folds(_fold_data(), seed=20260710)
    changed = _fold_data()
    features, labels = changed["AIB"]
    changed["AIB"] = (
        [replace(item, retrieval_margin=item.retrieval_margin + 100) for item in features],
        labels,
    )
    modified = fit_calibration_folds(changed, seed=20260710)

    before = next(fold for fold in original if fold.test_issuer == "AIB")
    after = next(fold for fold in modified if fold.test_issuer == "AIB")
    assert _frozen_state_bytes(before) == _frozen_state_bytes(after)


def test_changing_fit_labels_changes_fitted_coefficients() -> None:
    original = fit_calibration_folds(_fold_data(), seed=20260710)
    fit_fold = next(fold for fold in original if "AIB" in fold.split_manifest["fit_issuers"])
    changed = _fold_data()
    features, labels = changed["AIB"]
    changed["AIB"] = (features, [not value for value in labels])
    modified = fit_calibration_folds(changed, seed=20260710)
    changed_fold = next(fold for fold in modified if fold.test_issuer == fit_fold.test_issuer)

    assert (
        fit_fold.split_manifest["fitted_coefficients"]
        != changed_fold.split_manifest["fitted_coefficients"]
    )


def test_nested_protocol_requires_four_distinct_issuers() -> None:
    data = _fold_data()
    data.pop("KfW")
    with pytest.raises(ValueError, match="at least four issuers"):
        fit_calibration_folds(data)


def test_degenerate_fit_labels_fail_honestly() -> None:
    with pytest.raises(ValueError, match="both positive and negative"):
        PlattCalibrator.fit(_features(0.5), [True] * 8)


def test_final_calibration_rejects_nonconvergence() -> None:
    calibrator = PlattCalibrator.fit(
        _features(0.5),
        [True, False, True, False, True, False, True, False],
        max_iterations=1,
    )
    assert not calibrator.converged
    with pytest.raises(RuntimeError, match="did not converge"):
        require_final_calibration(calibrator)


def _result(method: str, evidence_id: str, score: float, *, verified: bool = True) -> RetrievalResult:
    return RetrievalResult(
        method=method,
        question_id="q1",
        evidence_id=evidence_id,
        rank=1,
        score=score,
        valid_time_match=True,
        verification_status="time_verified" if verified else "unverified",
    )


def test_feature_builder_requires_six_methods_and_uses_fixed_denominator() -> None:
    all_results = {
        "q1": {
            method: (_result(method, "same" if method != "dense" else "other", 1.0),)
            for method in REGISTERED_METHOD_IDS
        }
    }
    features = _build_features_for_question("q1", all_results, "temporal_kg_verify")
    assert features is not None
    assert features.cross_retriever_agreement == pytest.approx(5 / 6)

    del all_results["q1"]["dense"]
    with pytest.raises(RuntimeError, match="six-method"):
        _build_features_for_question("q1", all_results, "temporal_kg_verify")


def test_evidence_coverage_is_score_scale_invariant_and_bounded() -> None:
    def build(scale: float) -> dict[str, dict[str, tuple[RetrievalResult, ...]]]:
        methods: dict[str, tuple[RetrievalResult, ...]] = {}
        for method in REGISTERED_METHOD_IDS:
            methods[method] = tuple(
                replace(_result(method, f"e{index}", scale * (5 - index)), rank=index + 1)
                for index in range(3)
            )
        return {"q1": methods}

    low = _build_features_for_question("q1", build(1.0), "temporal_kg_verify")
    high = _build_features_for_question("q1", build(1000.0), "temporal_kg_verify")
    assert low is not None and high is not None
    assert low.evidence_coverage == high.evidence_coverage == pytest.approx(3 / 5)
    assert 0.0 <= low.evidence_coverage <= 1.0


class _ForbiddenEvaluatorField(dict[str, object]):
    def get(self, key: str, default: object = None) -> object:
        raise AssertionError(f"production feature accessed evaluator field {key}")

    def __getitem__(self, key: str) -> object:
        raise AssertionError(f"production feature accessed evaluator field {key}")


def test_production_features_do_not_access_forbidden_evaluator_fields() -> None:
    all_results = {
        "q1": {
            method: (_result(method, "gold-evidence", 1.0),)
            for method in REGISTERED_METHOD_IDS
        }
    }
    labels = EvaluatorGold(
        relevant_evidence={"q1": frozenset({"gold-evidence"})},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence=_ForbiddenEvaluatorField(),
        citation_evidence=_ForbiddenEvaluatorField(),
        expected_numeric=_ForbiddenEvaluatorField(),
    )

    fold_data = _build_fold_data(all_results, labels, "temporal_kg_verify")

    assert len(fold_data["AIB"][0]) == 1


@pytest.mark.parametrize(
    "primary_override",
    [
        {"verified": False},
        {"valid_time_match": False},
    ],
)
def test_correct_and_supported_target_requires_visible_support(
    primary_override: dict[str, bool],
) -> None:
    all_results = {
        "q1": {
            method: (_result(method, "gold-evidence", 1.0),)
            for method in REGISTERED_METHOD_IDS
        }
    }
    primary = all_results["q1"]["temporal_kg_verify"][0]
    if "verified" in primary_override:
        primary = replace(
            primary,
            verification_status=(
                "time_verified" if primary_override["verified"] else "unverified"
            ),
        )
    if "valid_time_match" in primary_override:
        primary = replace(
            primary,
            valid_time_match=primary_override["valid_time_match"],
        )
    all_results["q1"]["temporal_kg_verify"] = (primary,)
    labels = EvaluatorGold(
        relevant_evidence={"q1": frozenset({"gold-evidence"})},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={},
    )

    fold_data = _build_fold_data(all_results, labels, "temporal_kg_verify")

    assert fold_data["AIB"][1] == [False]


def test_decision_consumes_frozen_policy_and_temporal_gate() -> None:
    strict = DecisionPolicy(0.95, 0.20, 0.25)
    permissive = DecisionPolicy(0.80, 0.20, 0.25)

    strict_decision = decide(0.90, 0.80, True, True, strict)
    permissive_decision = decide(0.90, 0.80, True, True, permissive)
    stale_decision = decide(0.99, 0.90, True, False, permissive)

    assert strict_decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED
    assert permissive_decision.code is DecisionCode.AUTO_REPORT
    assert stale_decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED


def test_fold_manifest_contains_complete_frozen_decision_policy() -> None:
    folds = fit_calibration_folds(_fold_data(), seed=20260710)

    for fold in folds:
        assert fold.split_manifest["decision_policy"] == {
            "calibrated_probability_threshold": fold.decision_threshold,
            "conformal_threshold": fold.conformal_threshold,
            "evidence_sufficiency_threshold": 0.25,
            "extraction_validity_required": True,
            "temporal_validity_required": True,
        }


def test_final_decision_rejects_missing_frozen_policy_state() -> None:
    folds = fit_calibration_folds(_fold_data(), seed=20260710)
    damaged = tuple(
        replace(
            fold,
            split_manifest={
                key: value
                for key, value in fold.split_manifest.items()
                if key != "decision_policy"
            },
        )
        if fold.test_issuer == "AIB"
        else fold
        for fold in folds
    )
    all_results = {
        "q1": {
            method: (_result(method, "gold-evidence", 1.0),)
            for method in REGISTERED_METHOD_IDS
        }
    }
    labels = EvaluatorGold(
        relevant_evidence={"q1": frozenset({"gold-evidence"})},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={},
    )

    with pytest.raises(RuntimeError, match="incomplete frozen decision policy"):
        _run_decision_gating(all_results, labels, "temporal_kg_verify", damaged)


def test_hand_computed_small_sample_conformal_fixtures() -> None:
    assert compute_conformal_threshold([0.40], alpha=0.10) == pytest.approx(0.40)
    assert compute_conformal_threshold([0.10, 0.80], alpha=0.50) == pytest.approx(0.80)
    tied = compute_conformal_threshold([0.20, 0.20], alpha=0.50)
    assert tied == pytest.approx(0.20)
    assert conformal_accept(score=tied, threshold=tied) is True
    assert correctness_nonconformity(0.95, observed_correct=True) == pytest.approx(0.05)
    assert correctness_nonconformity(0.95, observed_correct=False) == pytest.approx(0.95)
    with pytest.raises(ValueError, match="non-empty"):
        compute_conformal_threshold([], alpha=0.10)
    for nonfinite in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="finite"):
            compute_conformal_threshold([nonfinite], alpha=0.10)


def test_selective_metrics_use_per_record_frozen_thresholds_and_null_abstention() -> None:
    metrics = selective_metrics_at_threshold(
        [0.90, 0.80],
        [True, False],
        [0.85, 0.85],
    )
    assert metrics == {
        "coverage": 0.5,
        "coverage_evaluable": True,
        "coverage_reason": None,
        "selective_risk": 0.0,
        "selective_risk_evaluable": True,
        "selective_risk_reason": None,
    }

    abstain_all = selective_metrics_at_threshold(
        [0.90, 0.80],
        [True, False],
        [0.95, 0.95],
    )
    assert abstain_all["coverage"] == 0.0
    assert abstain_all["selective_risk"] is None
    assert abstain_all["selective_risk_evaluable"] is False
    assert abstain_all["selective_risk_reason"] == "no_accepted_records"


def test_runner_emits_actual_outer_risk_coverage_and_selective_metrics() -> None:
    result = _run_calibration(_fold_data(), seed=20260710)

    curve = result["risk_coverage"]
    assert isinstance(curve, list)
    assert len(curve) == result["total_samples"]
    assert curve[-1]["coverage"] == pytest.approx(1.0)
    assert any(row["selective_risk"] > 0.0 for row in curve)
    assert result["selective_risk_at_threshold_evaluable"] is True
    assert result["selective_risk_at_threshold"] is not None


def test_hand_computed_metric_fixtures_and_singleton_aurc() -> None:
    probabilities = [0.90, 0.60]
    labels = [True, False]

    assert brier_score(probabilities, labels) == pytest.approx(0.185)
    assert expected_calibration_error(probabilities, labels, n_bins=2) == pytest.approx(0.25)
    assert risk_coverage_curve(probabilities, labels) == pytest.approx(
        [(0.5, 0.0), (1.0, 0.5)]
    )
    assert area_under_risk_coverage(probabilities, labels) == pytest.approx(0.125)
    assert area_under_risk_coverage([0.90], [False]) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "metric",
    [
        brier_score,
        expected_calibration_error,
        risk_coverage_curve,
        area_under_risk_coverage,
    ],
)
def test_metrics_reject_misaligned_and_nonfinite_inputs(metric: object) -> None:
    with pytest.raises(ValueError, match="align"):
        metric([0.9, 0.8], [True])  # type: ignore[operator]
    with pytest.raises(ValueError, match="finite"):
        metric([float("nan")], [True])  # type: ignore[operator]
