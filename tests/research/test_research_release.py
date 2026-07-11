"""Integration tests for the EcoQuant temporal risk intelligence study.

Loads each results JSON artifact produced by ``scripts/run_research.py`` and
asserts structural validity: correct keys present, non-empty collections, and
metric values within reasonable ranges.  These tests guard against silent data
corruption or schema drift before publication.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RESULTS_DIR = Path(__file__).resolve().parents[2] / "research" / "results"

# ---------------------------------------------------------------------------
# Expected structure
# ---------------------------------------------------------------------------

_EXPECTED_METHODS = {
    "bm25",
    "dense",
    "static_kg",
    "temporal_kg",
    "temporal_kg_rerank",
    "temporal_kg_verify",
}

_RETRIEVAL_METRIC_KEYS = {
    "recall_at_5",
    "hit_at_5",
    "mrr",
    "ndcg_at_5",
    "temporal_accuracy",
    "stale_evidence_rate",
    "contradiction_f1",
    "citation_accuracy",
    "recall_evaluable_question_count",
    "zero_gold_question_count",
}

_CALIBRATION_FOLD_KEYS = {
    "test_issuer",
    "train_issuers",
    "test_sample_count",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(name: str) -> dict:
    path = RESULTS_DIR / name
    assert path.exists(), f"Missing results file: {path}"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# study_manifest.json
# ---------------------------------------------------------------------------

class TestStudyManifest:
    """The study manifest records run parameters."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.manifest = _load("study_manifest.json")

    def test_has_seed(self) -> None:
        assert "seed" in self.manifest
        assert isinstance(self.manifest["seed"], int)

    def test_corpus_size_positive(self) -> None:
        assert self.manifest["corpus_size"] > 0

    def test_question_count_positive(self) -> None:
        assert self.manifest["question_count"] > 0

    def test_methods_match_registry(self) -> None:
        methods = set(self.manifest["methods"])
        assert methods == _EXPECTED_METHODS

    def test_implementation_mode(self) -> None:
        assert self.manifest["implementation_mode"] == "production"


# ---------------------------------------------------------------------------
# retrieval_metrics.json
# ---------------------------------------------------------------------------

class TestRetrievalMetrics:
    """Per-method retrieval metrics across all questions."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.metrics = _load("retrieval_metrics.json")

    def test_all_methods_present(self) -> None:
        assert set(self.metrics.keys()) == _EXPECTED_METHODS

    def test_each_method_has_required_keys(self) -> None:
        for method, scores in self.metrics.items():
            assert set(scores.keys()) == _RETRIEVAL_METRIC_KEYS, (
                f"Method {method} missing keys: {_RETRIEVAL_METRIC_KEYS - set(scores.keys())}"
            )

    def test_rate_metrics_in_unit_interval(self) -> None:
        rate_keys = [
            "recall_at_5",
            "hit_at_5",
            "mrr",
            "ndcg_at_5",
            "temporal_accuracy",
            "stale_evidence_rate",
            "contradiction_f1",
            "citation_accuracy",
        ]
        for method, scores in self.metrics.items():
            for key in rate_keys:
                val = scores[key]
                assert 0.0 <= val <= 1.0, (
                    f"{method}.{key} = {val} outside [0, 1]"
                )

    def test_evaluable_question_count_positive(self) -> None:
        for method, scores in self.metrics.items():
            assert scores["recall_evaluable_question_count"] > 0
            assert scores["zero_gold_question_count"] == 0

    def test_temporal_kg_verify_stale_rate_zero(self) -> None:
        """The primary method must have zero stale evidence."""
        assert self.metrics["temporal_kg_verify"]["stale_evidence_rate"] == 0.0


# ---------------------------------------------------------------------------
# calibration_result.json
# ---------------------------------------------------------------------------

class TestCalibrationResult:
    """Leave-one-issuer-out calibration output."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.result = _load("calibration_result.json")

    def test_required_top_level_keys(self) -> None:
        required = {
            "frozen_threshold",
            "brier",
            "ece",
            "aurc",
            "coverage_at_threshold",
            "fold_count",
            "total_samples",
            "folds",
        }
        assert required.issubset(set(self.result.keys()))

    def test_threshold_in_unit_interval(self) -> None:
        t = self.result["frozen_threshold"]
        assert 0.0 <= t <= 1.0

    def test_brier_in_unit_interval(self) -> None:
        assert 0.0 <= self.result["brier"] <= 1.0

    def test_ece_in_unit_interval(self) -> None:
        assert 0.0 <= self.result["ece"] <= 1.0

    def test_aurc_in_unit_interval(self) -> None:
        assert 0.0 <= self.result["aurc"] <= 1.0

    def test_coverage_in_unit_interval(self) -> None:
        assert 0.0 <= self.result["coverage_at_threshold"] <= 1.0

    def test_fold_count_matches_folds(self) -> None:
        assert self.result["fold_count"] == len(self.result["folds"])

    def test_total_samples_positive(self) -> None:
        assert self.result["total_samples"] > 0

    def test_fold_structure(self) -> None:
        for fold in self.result["folds"]:
            assert set(fold.keys()) == _CALIBRATION_FOLD_KEYS
            assert fold["test_sample_count"] > 0
            assert isinstance(fold["train_issuers"], list)
            assert len(fold["train_issuers"]) > 0

    def test_folds_cover_four_issuers(self) -> None:
        test_issuers = {f["test_issuer"] for f in self.result["folds"]}
        assert len(test_issuers) == 4

    def test_test_issuer_excluded_from_train(self) -> None:
        for fold in self.result["folds"]:
            assert fold["test_issuer"] not in fold["train_issuers"]


# ---------------------------------------------------------------------------
# decision_summary.json
# ---------------------------------------------------------------------------

class TestDecisionSummary:
    """Decision gating output for the primary method."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.summary = _load("decision_summary.json")

    def test_required_keys(self) -> None:
        required = {
            "total_questions",
            "auto_report_count",
            "human_review_required_count",
            "insufficient_evidence_count",
            "conformal_threshold",
        }
        assert required == set(self.summary.keys())

    def test_counts_non_negative(self) -> None:
        for key in (
            "auto_report_count",
            "human_review_required_count",
            "insufficient_evidence_count",
        ):
            assert self.summary[key] >= 0, f"{key} is negative"

    def test_counts_sum_to_total(self) -> None:
        total = self.summary["total_questions"]
        parts = (
            self.summary["auto_report_count"]
            + self.summary["human_review_required_count"]
            + self.summary["insufficient_evidence_count"]
        )
        assert parts == total

    def test_conformal_threshold_reasonable(self) -> None:
        t = self.summary["conformal_threshold"]
        assert 0.0 <= t <= 1.0


# ---------------------------------------------------------------------------
# bootstrap_intervals.json
# ---------------------------------------------------------------------------

class TestBootstrapIntervals:
    """Paired bootstrap confidence intervals."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.intervals = _load("bootstrap_intervals.json")

    def test_has_comparison_key(self) -> None:
        assert "temporal_kg_verify_vs_bm25" in self.intervals

    def test_interval_structure(self) -> None:
        entry = self.intervals["temporal_kg_verify_vs_bm25"]
        assert entry["metric"] == "top1_accuracy"
        assert isinstance(entry["point_estimate"], (int, float))
        assert isinstance(entry["lower"], (int, float))
        assert isinstance(entry["upper"], (int, float))
        assert isinstance(entry["seed"], int)
        assert isinstance(entry["samples"], int)
        assert isinstance(entry["cluster_count"], int)

    def test_interval_bounds_ordered(self) -> None:
        entry = self.intervals["temporal_kg_verify_vs_bm25"]
        assert entry["lower"] <= entry["point_estimate"] <= entry["upper"]

    def test_samples_positive(self) -> None:
        assert self.intervals["temporal_kg_verify_vs_bm25"]["samples"] > 0

    def test_cluster_count_positive(self) -> None:
        assert self.intervals["temporal_kg_verify_vs_bm25"]["cluster_count"] > 0


# ---------------------------------------------------------------------------
# Cross-artifact consistency
# ---------------------------------------------------------------------------

class TestCrossArtifactConsistency:
    """Sanity checks across multiple result files."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.manifest = _load("study_manifest.json")
        self.decisions = _load("decision_summary.json")
        self.calibration = _load("calibration_result.json")
        self.intervals = _load("bootstrap_intervals.json")

    def test_question_count_matches_decisions(self) -> None:
        assert self.manifest["question_count"] == self.decisions["total_questions"]

    def test_calibration_threshold_matches_decisions(self) -> None:
        assert self.calibration["frozen_threshold"] == pytest.approx(
            self.decisions["conformal_threshold"]
        )

    def test_bootstrap_seed_matches_manifest(self) -> None:
        entry = self.intervals["temporal_kg_verify_vs_bm25"]
        assert entry["seed"] == self.manifest["seed"]
