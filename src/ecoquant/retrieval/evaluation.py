"""Comparable retrieval metrics and deterministic issuer-clustered intervals."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .base import RetrievalResult


BOOTSTRAP_SEED = 20260710


@dataclass(frozen=True)
class EvaluationLabels:
    """Held-out evaluation annotations; never part of a retriever interface."""

    relevant_evidence: Mapping[str, frozenset[str]]
    issuer_by_question: Mapping[str, str]
    contradiction_evidence: Mapping[str, frozenset[str]]
    citation_evidence: Mapping[str, frozenset[str]]
    expected_numeric: Mapping[str, float]


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_5: float
    mrr: float
    ndcg_at_5: float
    temporal_accuracy: float
    stale_evidence_rate: float
    contradiction_f1: float
    citation_accuracy: float
    numerical_mismatch: float


@dataclass(frozen=True)
class BootstrapInterval:
    point_estimate: float
    lower: float
    upper: float
    seed: int
    samples: int
    cluster_count: int


def score_retrieval(
    results_by_question: Mapping[str, Sequence[RetrievalResult]],
    labels: EvaluationLabels,
    *,
    numeric_predictions: Mapping[str, float] | None = None,
) -> RetrievalMetrics:
    """Compute method-neutral retrieval and audit metrics over labelled outputs."""

    question_ids = tuple(sorted(labels.relevant_evidence))
    if not question_ids:
        raise ValueError("at least one labelled question is required")

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    temporal: list[float] = []
    citations: list[float] = []
    predicted_contradictions: set[tuple[str, str]] = set()
    expected_contradictions: set[tuple[str, str]] = set()
    stale_count = 0
    retrieved_count = 0

    for question_id in question_ids:
        results = tuple(sorted(results_by_question.get(question_id, ()), key=lambda result: result.rank))[:5]
        relevant = labels.relevant_evidence[question_id]
        hit_ranks = [result.rank for result in results if result.evidence_id in relevant]
        recalls.append(len({result.evidence_id for result in results} & relevant) / len(relevant) if relevant else 0.0)
        reciprocal_ranks.append(1.0 / min(hit_ranks) if hit_ranks else 0.0)
        ideal = min(len(relevant), 5)
        dcg = sum(1.0 / math.log2(rank + 1) for rank in hit_ranks)
        ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal + 1))
        ndcgs.append(dcg / ideal_dcg if ideal_dcg else 0.0)
        temporal.append(float(bool(results) and results[0].valid_time_match))
        citations.append(float(bool(results) and results[0].evidence_id in labels.citation_evidence.get(question_id, frozenset())))
        stale_count += sum(not result.valid_time_match for result in results)
        retrieved_count += len(results)
        predicted_contradictions.update(
            (question_id, result.evidence_id) for result in results if result.verification_status == "contradiction"
        )
        expected_contradictions.update(
            (question_id, evidence_id) for evidence_id in labels.contradiction_evidence.get(question_id, frozenset())
        )

    mismatch_values: list[float] = []
    if labels.expected_numeric:
        if numeric_predictions is None or any(question_id not in numeric_predictions for question_id in labels.expected_numeric):
            mismatch_values = [math.inf]
        else:
            mismatch_values = [
                abs(numeric_predictions[question_id] - expected)
                for question_id, expected in labels.expected_numeric.items()
            ]
    return RetrievalMetrics(
        recall_at_5=_mean(recalls),
        mrr=_mean(reciprocal_ranks),
        ndcg_at_5=_mean(ndcgs),
        temporal_accuracy=_mean(temporal),
        stale_evidence_rate=stale_count / retrieved_count if retrieved_count else 0.0,
        contradiction_f1=_f1(predicted_contradictions, expected_contradictions),
        citation_accuracy=_mean(citations),
        numerical_mismatch=_mean(mismatch_values),
    )


def paired_issuer_clustered_bootstrap(
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    issuer_by_question: Mapping[str, str],
    *,
    samples: int = 1_000,
) -> BootstrapInterval:
    """Bootstrap paired differences by resampling issuer clusters, not rows."""

    if samples < 1:
        raise ValueError("samples must be at least 1")
    if set(baseline) != set(candidate) or set(baseline) != set(issuer_by_question):
        raise ValueError("baseline, candidate, and issuer mappings must share question ids")
    clusters: dict[str, list[str]] = defaultdict(list)
    for question_id in sorted(baseline):
        clusters[issuer_by_question[question_id]].append(question_id)
    cluster_ids = tuple(sorted(clusters))
    if not cluster_ids:
        raise ValueError("at least one issuer cluster is required")

    point_estimate = _mean([candidate[qid] - baseline[qid] for qid in sorted(baseline)])
    generator = random.Random(BOOTSTRAP_SEED)
    differences: list[float] = []
    for _ in range(samples):
        sampled_questions = [qid for _ in cluster_ids for qid in clusters[generator.choice(cluster_ids)]]
        differences.append(_mean([candidate[qid] - baseline[qid] for qid in sampled_questions]))
    ordered = sorted(differences)
    return BootstrapInterval(
        point_estimate=point_estimate,
        lower=_quantile(ordered, 0.025),
        upper=_quantile(ordered, 0.975),
        seed=BOOTSTRAP_SEED,
        samples=samples,
        cluster_count=len(cluster_ids),
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _f1(predicted: set[tuple[str, str]], expected: set[tuple[str, str]]) -> float:
    if not predicted and not expected:
        return 1.0
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _quantile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)
