"""E5: build UncertaintyFeatures from retrieval results + correctness labels.

For each (question, method) pair, we derive five uncertainty features from the
ranked retrieval results:

- ``retrieval_margin``: top-1 score minus top-2 score (0 if only one result).
- ``cross_retriever_agreement``: fraction of methods whose top-1 evidence_id
  matches this method's top-1.
- ``extraction_confidence``: the top-1 score, min-max normalized per question.
- ``temporal_validity``: 1.0 if the top-1 result's valid_time_match is True.
- ``evidence_coverage``: fraction of gold evidence retrieved at rank <= 5.

The correctness label is whether the method's top-1 evidence is relevant
(a hit). These features/labels feed the existing calibrated-abstention
machinery (``fit_calibration_folds``, ``selective_metrics_at_threshold``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ecoquant.retrieval.base import RetrievalResult
from ecoquant.uncertainty.features import UncertaintyFeatures

TOP_K = 5


def build_features_from_retrieval(
    results_by_method: Mapping[str, Mapping[str, Sequence[RetrievalResult]]],
    relevant_by_question: Mapping[str, frozenset[str]],
) -> tuple[list[UncertaintyFeatures], list[bool]]:
    """Build (features, labels) for every (question, method) pair.

    Args:
        results_by_method: {method: {question_id: ranked RetrievalResult}}.
        relevant_by_question: {question_id: frozenset(gold evidence_ids)}.

    Returns:
        (features, labels) aligned; one entry per (question, method) pair.
    """
    methods = tuple(results_by_method)
    question_ids = tuple(sorted(relevant_by_question))

    # Per-question top-1 evidence across methods (for cross-retriever agreement).
    top1_by_question: dict[str, list[str]] = {
        qid: [
            results_by_method[method][qid][0].evidence_id
            for method in methods
            if results_by_method[method].get(qid)
        ]
        for qid in question_ids
    }

    features: list[UncertaintyFeatures] = []
    labels: list[bool] = []
    for qid in question_ids:
        relevant = relevant_by_question[qid]
        # Min-max normalization per question across methods.
        top1_scores = [
            results_by_method[method][qid][0].score
            for method in methods
            if results_by_method[method].get(qid)
        ]
        lo, hi = (min(top1_scores), max(top1_scores)) if top1_scores else (0.0, 1.0)
        span = (hi - lo) or 1.0

        for method in methods:
            ranked = results_by_method[method].get(qid, ())
            if not ranked:
                continue
            top1 = ranked[0]
            top1_score = top1.score
            top2_score = ranked[1].score if len(ranked) > 1 else None
            margin = (top1_score - top2_score) if top2_score is not None else 0.0

            agreement = sum(
                1 for other_top1 in top1_by_question[qid]
                if other_top1 == top1.evidence_id
            ) / max(1, len(top1_by_question[qid]))

            extracted = (top1_score - lo) / span
            retrieved_ids = {result.evidence_id for result in ranked}
            coverage = len(retrieved_ids & relevant) / len(relevant) if relevant else 0.0

            features.append(UncertaintyFeatures(
                retrieval_margin=margin,
                cross_retriever_agreement=agreement,
                extraction_confidence=extracted,
                temporal_validity=1.0 if top1.valid_time_match else 0.0,
                evidence_coverage=coverage,
            ))
            labels.append(bool(top1.evidence_id in relevant))
    return features, labels
