"""Comparable retrieval metrics and deterministic issuer-clustered intervals."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .base import RetrievalResult


BOOTSTRAP_SEED = 20260710


@dataclass(frozen=True)
class EvidenceLocation:
    """Immutable page/block identity resolved from the retrieval evidence catalog."""

    page_id: str
    block_id: str


@dataclass(frozen=True)
class EvaluatorGold:
    """Held-out evaluation annotations; never part of a retriever interface."""

    relevant_evidence: Mapping[str, frozenset[str]]
    issuer_by_question: Mapping[str, str]
    contradiction_evidence: Mapping[str, frozenset[str]]
    citation_evidence: Mapping[str, frozenset[str]]
    expected_numeric: Mapping[str, float]
    gold_page_ids: Mapping[str, frozenset[str]] = field(default_factory=dict)
    gold_block_ids: Mapping[str, frozenset[str]] = field(default_factory=dict)


# Compatibility name for the previously public evaluator-only record.
EvaluationLabels = EvaluatorGold


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_5: float
    hit_at_5: float
    recall_evaluable_question_count: int
    zero_gold_question_count: int
    mrr: float
    ndcg_at_5: float
    temporal_accuracy: float
    stale_evidence_rate: float
    contradiction_f1: float | None
    contradiction_evaluable: bool
    contradiction_reason: str | None
    citation_accuracy: float
    page_accuracy_at_5: float | None
    block_accuracy_at_5: float | None
    evaluable_page_questions: int
    evaluable_block_questions: int
    non_evaluable_page_questions: int
    non_evaluable_block_questions: int
    page_accuracy_reason: str | None
    block_accuracy_reason: str | None
    numerical_mismatch: float
    evaluable_question_count: int
    prediction_count: int
    answer_coverage: float
    mismatch_count: int
    mismatch_denominator: int
    mismatch_rate: float


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
    labels: EvaluatorGold,
    *,
    numeric_predictions: Mapping[str, float] | None = None,
    evidence_catalog: Mapping[str, EvidenceLocation] | None = None,
) -> RetrievalMetrics:
    """Compute method-neutral retrieval and audit metrics over labelled outputs."""

    question_ids = tuple(sorted(labels.relevant_evidence))
    if not question_ids:
        raise ValueError("at least one labelled question is required")

    recalls: list[float] = []
    hits: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    temporal: list[float] = []
    citations: list[float] = []
    page_hits: list[float] = []
    block_hits: list[float] = []
    predicted_contradictions: set[tuple[str, str]] = set()
    expected_contradictions: set[tuple[str, str]] = set()
    stale_count = 0
    retrieved_count = 0

    for question_id in question_ids:
        results = tuple(sorted(results_by_question.get(question_id, ()), key=lambda result: result.rank))[:5]
        relevant = labels.relevant_evidence[question_id]
        retrieved_ids = {result.evidence_id for result in results}
        hit_ranks = [result.rank for result in results if result.evidence_id in relevant]
        hits.append(float(bool(retrieved_ids & relevant)))
        if relevant:
            recalls.append(len(retrieved_ids & relevant) / len(relevant))
        reciprocal_ranks.append(1.0 / min(hit_ranks) if hit_ranks else 0.0)
        ideal = min(len(relevant), 5)
        dcg = sum(1.0 / math.log2(rank + 1) for rank in hit_ranks)
        ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal + 1))
        ndcgs.append(dcg / ideal_dcg if ideal_dcg else 0.0)
        temporal.append(float(bool(results) and results[0].valid_time_match))
        citations.append(float(bool(results) and results[0].evidence_id in labels.citation_evidence.get(question_id, frozenset())))
        gold_pages = labels.gold_page_ids.get(question_id, frozenset())
        gold_blocks = labels.gold_block_ids.get(question_id, frozenset())
        if gold_pages or gold_blocks:
            catalog = evidence_catalog or {}
            missing_ids = sorted(result.evidence_id for result in results if result.evidence_id not in catalog)
            if missing_ids:
                raise ValueError(
                    f"missing evidence catalog entry for returned evidence: {', '.join(missing_ids)}"
                )
            locations = tuple(catalog[result.evidence_id] for result in results)
            if gold_pages:
                page_hits.append(float(any(location.page_id in gold_pages for location in locations)))
            if gold_blocks:
                block_hits.append(float(any(location.block_id in gold_blocks for location in locations)))
        stale_count += sum(not result.valid_time_match for result in results)
        retrieved_count += len(results)
        predicted_contradictions.update(
            (question_id, result.evidence_id) for result in results if result.verification_status == "contradiction"
        )
        expected_contradictions.update(
            (question_id, evidence_id) for evidence_id in labels.contradiction_evidence.get(question_id, frozenset())
        )

    predictions = numeric_predictions or {}
    numeric_question_ids = tuple(sorted(labels.expected_numeric))
    prediction_count = sum(question_id in predictions for question_id in numeric_question_ids)
    mismatch_count = sum(
        not _numeric_prediction_matches(predictions.get(question_id), labels.expected_numeric[question_id])
        for question_id in numeric_question_ids
    )
    mismatch_denominator = len(numeric_question_ids)
    mismatch_rate = mismatch_count / mismatch_denominator if mismatch_denominator else 0.0
    contradiction_f1 = _f1(predicted_contradictions, expected_contradictions)
    return RetrievalMetrics(
        recall_at_5=_mean(recalls),
        hit_at_5=_mean(hits),
        recall_evaluable_question_count=len(recalls),
        zero_gold_question_count=len(question_ids) - len(recalls),
        mrr=_mean(reciprocal_ranks),
        ndcg_at_5=_mean(ndcgs),
        temporal_accuracy=_mean(temporal),
        stale_evidence_rate=stale_count / retrieved_count if retrieved_count else 0.0,
        contradiction_f1=contradiction_f1,
        contradiction_evaluable=contradiction_f1 is not None,
        contradiction_reason=None if contradiction_f1 is not None else "no_positive_reference_or_prediction",
        citation_accuracy=_mean(citations),
        page_accuracy_at_5=_mean(page_hits) if page_hits else None,
        block_accuracy_at_5=_mean(block_hits) if block_hits else None,
        evaluable_page_questions=len(page_hits),
        evaluable_block_questions=len(block_hits),
        non_evaluable_page_questions=len(question_ids) - len(page_hits),
        non_evaluable_block_questions=len(question_ids) - len(block_hits),
        page_accuracy_reason=None if page_hits else "no_gold_page_annotations",
        block_accuracy_reason=None if block_hits else "no_gold_block_annotations",
        numerical_mismatch=mismatch_rate,
        evaluable_question_count=mismatch_denominator,
        prediction_count=prediction_count,
        answer_coverage=prediction_count / mismatch_denominator if mismatch_denominator else 0.0,
        mismatch_count=mismatch_count,
        mismatch_denominator=mismatch_denominator,
        mismatch_rate=mismatch_rate,
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


def _numeric_prediction_matches(prediction: object | None, expected: float) -> bool:
    """A numeric answer is either correct (0) or a mismatch (1)."""
    if prediction is None or isinstance(prediction, bool):
        return False
    try:
        parsed = float(prediction)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed) and math.isclose(parsed, expected, rel_tol=0.0, abs_tol=1e-9)


def _f1(predicted: set[tuple[str, str]], expected: set[tuple[str, str]]) -> float | None:
    """Compute F1 score.

    When neither predictions nor labels contain contradictions, returns None
    so strict JSON serialization remains portable.
    """
    if not predicted and not expected:
        return None
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
