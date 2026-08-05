"""E5 (rebuilt): leak-free uncertainty features from retrieval results.

**Leak-free contract (enforced by tests/research/test_no_gold_in_features.py):**

- ``build_features_from_retrieval`` takes ONLY retrieval results. It never
  accepts or reads gold relevance, gold evidence, gold pages, gold answers, or
  gold programs.
- Correctness labels are computed by ``labels_from_gold`` — an EXPLICITLY
  EVALUATION-ONLY function (gold is legitimate for evaluation, never for
  feature construction, calibration, threshold selection, or inference).

The previous version computed ``evidence_coverage`` as
``len(retrieved & gold_relevant) / len(gold_relevant)`` — a gold-derived
feature that is unavailable at inference time. That result is
INVALIDATED_GOLD_FEATURE_LEAKAGE (see docs/audits/E5_GOLD_LEAKAGE_AUDIT.md).

Features (all inference-time available):

- ``retrieval_margin``: top-1 minus top-2 score.
- ``cross_retriever_agreement``: fraction of methods agreeing on top-1.
- ``extraction_confidence``: min-max normalized top-1 score per question.
- ``temporal_validity``: 1.0 if the top-1 result's valid_time_match is True.
- ``evidence_coverage``: DEPRECATED placeholder = 0.0 (the gold-derived
  version is removed). Phase 11 defines the real leak-free coverage feature
  (predicted requirement coverage, not gold).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ecoquant.retrieval.base import RetrievalResult
from ecoquant.uncertainty.features import UncertaintyFeatures

TOP_K = 5


def build_features_from_retrieval(
    results_by_method: Mapping[str, Mapping[str, Sequence[RetrievalResult]]],
) -> list[UncertaintyFeatures]:
    """Build leak-free uncertainty features from retrieval results only.

    Args:
        results_by_method: {method: {question_id: ranked RetrievalResult}}.
            MUST NOT contain gold relevance/evidence/answers.

    Returns:
        One UncertaintyFeatures per (question, method) pair.
    """
    methods = tuple(results_by_method)
    question_ids = tuple(sorted({qid for by_q in results_by_method.values() for qid in by_q}))

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
    for qid in question_ids:
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
            top2_score = ranked[1].score if len(ranked) > 1 else None
            margin = (top1.score - top2_score) if top2_score is not None else 0.0
            agreement = sum(
                1 for other_top1 in top1_by_question[qid]
                if other_top1 == top1.evidence_id
            ) / max(1, len(top1_by_question[qid]))
            extracted = (top1.score - lo) / span

            features.append(UncertaintyFeatures(
                retrieval_margin=margin,
                cross_retriever_agreement=agreement,
                extraction_confidence=extracted,
                temporal_validity=1.0 if top1.valid_time_match else 0.0,
                evidence_coverage=0.0,  # placeholder; gold-derived version removed
            ))
    return features


def labels_from_gold(
    results_by_method: Mapping[str, Mapping[str, Sequence[RetrievalResult]]],
    relevant_by_question: Mapping[str, frozenset[str]],
) -> list[bool]:
    """EVALUATION-ONLY: correctness labels from gold relevance.

    This function exists so gold use is explicit and confined to evaluation.
    It is never called inside feature construction, calibration fitting,
    threshold selection, or inference.
    """
    labels: list[bool] = []
    for qid in sorted(relevant_by_question):
        relevant = relevant_by_question[qid]
        for method in results_by_method:
            ranked = results_by_method[method].get(qid, ())
            if not ranked:
                continue
            labels.append(bool(ranked[0].evidence_id in relevant))
    return labels
