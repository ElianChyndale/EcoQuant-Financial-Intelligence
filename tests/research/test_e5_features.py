from __future__ import annotations

import math
from pathlib import Path

import pytest

from ecoquant.research.calibration_eval.features import (
    build_features_from_retrieval,
    labels_from_gold,
)
from ecoquant.uncertainty.features import UncertaintyFeatures

ROOT = Path(__file__).resolve().parents[2]


def _synthetic_retrieval():
    """Minimal retrieval-shaped results: method -> {question_id: ranked results}."""
    from ecoquant.retrieval.base import RetrievalResult

    # 4 questions, 2 methods; Q1/Q2 correct (hit), Q3/Q4 wrong.
    results = {
        "bm25": {
            "q1": (RetrievalResult("bm25", "q1", "ev-a", 1, 0.9, True, "unverified"),
                   RetrievalResult("bm25", "q1", "ev-b", 2, 0.5, True, "unverified")),
            "q2": (RetrievalResult("bm25", "q2", "ev-c", 1, 0.8, True, "unverified"),),
            "q3": (RetrievalResult("bm25", "q3", "ev-x", 1, 0.7, True, "unverified"),
                   RetrievalResult("bm25", "q3", "ev-a", 2, 0.6, True, "unverified")),
            "q4": (RetrievalResult("bm25", "q4", "ev-y", 1, 0.6, True, "unverified"),),
        },
        "dense": {
            "q1": (RetrievalResult("dense", "q1", "ev-a", 1, 0.95, True, "unverified"),),
            "q2": (RetrievalResult("dense", "q2", "ev-c", 1, 0.7, True, "unverified"),),
            "q3": (RetrievalResult("dense", "q3", "ev-z", 1, 0.65, True, "unverified"),),
            "q4": (RetrievalResult("dense", "q4", "ev-w", 1, 0.55, True, "unverified"),),
        },
    }
    gold = {
        "q1": frozenset({"ev-a"}), "q2": frozenset({"ev-c"}),
        "q3": frozenset({"ev-a"}), "q4": frozenset({"ev-c"}),
    }
    return results, gold


def test_features_shape_and_labels() -> None:
    results, gold = _synthetic_retrieval()
    features = build_features_from_retrieval(results)
    labels = labels_from_gold(results, gold)
    # 4 questions x 2 methods = 8 feature vectors
    assert len(features) == 8
    assert len(labels) == 8
    assert all(isinstance(f, UncertaintyFeatures) for f in features)
    assert all(isinstance(l, bool) for l in labels)


def test_correctness_labels_match_hits() -> None:
    results, gold = _synthetic_retrieval()
    labels = labels_from_gold(results, gold)
    # q1/q2 top-1 hits -> True; q3/q4 top-1 misses -> False
    # 2 methods x (2 correct + 2 wrong)
    assert labels.count(True) == 4
    assert labels.count(False) == 4


def test_features_are_finite() -> None:
    results, gold = _synthetic_retrieval()
    features = build_features_from_retrieval(results)
    for f in features:
        for value in (f.retrieval_margin, f.cross_retriever_agreement,
                      f.extraction_confidence, f.temporal_validity, f.evidence_coverage):
            assert math.isfinite(value)


def test_feature_builder_ignores_gold() -> None:
    """The feature builder takes no gold input and never changes with gold."""
    results, gold = _synthetic_retrieval()
    features_a = build_features_from_retrieval(results)
    # Mutating gold must not change features (they are gold-independent).
    mutated_gold = {qid: frozenset({"ev-other"}) for qid in gold}
    labels_a = labels_from_gold(results, gold)
    labels_b = labels_from_gold(results, mutated_gold)
    assert features_a == build_features_from_retrieval(results)
    assert labels_a != labels_b  # labels DO change with gold (evaluation-only)
