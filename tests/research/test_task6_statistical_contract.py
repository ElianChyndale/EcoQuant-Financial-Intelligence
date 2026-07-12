"""Authoritative statistical contract tests for the Task 6 repair."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from ecoquant.retrieval.base import REGISTERED_METHOD_IDS, RetrievalResult
from ecoquant.uncertainty.calibration import (
    PlattCalibrator,
    fit_calibration_folds,
    require_final_calibration,
)
from ecoquant.uncertainty.conformal import (
    candidate_correctness_nonconformity,
    correctness_nonconformity,
)
from ecoquant.uncertainty.decision import DecisionCode, DecisionPolicy, decide
from ecoquant.uncertainty.features import UncertaintyFeatures
from scripts.run_research import _build_features_for_question


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


def test_outer_mutation_does_not_change_its_fold_frozen_state() -> None:
    original = fit_calibration_folds(_fold_data(), seed=20260710)
    changed = _fold_data()
    features, labels = changed["AIB"]
    changed["AIB"] = ([replace(item, retrieval_margin=item.retrieval_margin + 100) for item in features], [not x for x in labels])
    modified = fit_calibration_folds(changed, seed=20260710)

    before = next(fold for fold in original if fold.test_issuer == "AIB")
    after = next(fold for fold in modified if fold.test_issuer == "AIB")
    assert before.calibrator == after.calibrator
    assert before.normalization == after.normalization
    assert before.conformal_threshold == after.conformal_threshold
    assert before.decision_threshold == after.decision_threshold


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


def test_decision_consumes_frozen_policy_and_temporal_gate() -> None:
    strict = DecisionPolicy(0.95, 0.20, 0.25)
    permissive = DecisionPolicy(0.80, 0.20, 0.25)

    strict_decision = decide(0.90, 0.80, True, True, strict)
    permissive_decision = decide(0.90, 0.80, True, True, permissive)
    stale_decision = decide(0.99, 0.90, True, False, permissive)

    assert strict_decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED
    assert permissive_decision.code is DecisionCode.AUTO_REPORT
    assert stale_decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED
