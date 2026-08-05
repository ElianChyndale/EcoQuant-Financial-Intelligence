"""FinVEST A1 retrieval metrics (question/issuer as unit; no per-retriever inflation).

Metrics: Document Recall@k, Unit Recall@k (All-Required-Evidence Recall),
MRR, nDCG, Requirement Coverage (predicted), set precision, redundancy.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .full_corpus import RankedResult


def all_required_evidence_recall(
    ranked: Sequence[RankedResult],
    gold_evidence_ids: frozenset[str],
    *,
    k: int = 20,
) -> float:
    """Fraction of gold evidence units retrieved at rank <= k."""
    if not gold_evidence_ids:
        return 1.0  # no required evidence (unanswerable) — trivially satisfied
    retrieved = {r.evidence_id for r in ranked[:k]}
    return len(retrieved & gold_evidence_ids) / len(gold_evidence_ids)


def document_recall_at_k(
    ranked: Sequence[RankedResult],
    gold_document_ids: frozenset[str],
    *,
    k: int = 5,
) -> float:
    """Fraction of gold documents with >=1 unit retrieved at rank <= k."""
    if not gold_document_ids:
        return 1.0
    retrieved_docs = {r.document_id for r in ranked[:k]}
    return len(retrieved_docs & gold_document_ids) / len(gold_document_ids)


def mrr(ranked: Sequence[RankedResult], gold_evidence_ids: frozenset[str]) -> float:
    """Reciprocal rank of the first gold evidence."""
    for result in ranked:
        if result.evidence_id in gold_evidence_ids:
            return 1.0 / result.rank
    return 0.0


def ndcg_at_k(
    ranked: Sequence[RankedResult],
    gold_evidence_ids: frozenset[str],
    *,
    k: int = 20,
) -> float:
    """nDCG@k with binary relevance (gold evidence = relevant)."""
    hits = [1.0 if r.evidence_id in gold_evidence_ids else 0.0 for r in ranked[:k]]
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, start=1))
    ideal_count = min(len(gold_evidence_ids), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def set_precision(
    ranked: Sequence[RankedResult],
    gold_evidence_ids: frozenset[str],
    *,
    k: int = 20,
) -> float:
    """Fraction of retrieved units that are gold evidence."""
    if not ranked:
        return 0.0
    retrieved = {r.evidence_id for r in ranked[:k]}
    return len(retrieved & gold_evidence_ids) / len(retrieved)


def redundancy(
    ranked: Sequence[RankedResult],
    *,
    k: int = 20,
) -> float:
    """Fraction of retrieved units sharing a document (redundancy proxy)."""
    if not ranked:
        return 0.0
    docs = [r.document_id for r in ranked[:k]]
    unique = len(set(docs))
    return 1.0 - (unique / len(docs)) if docs else 0.0


def evaluate_retrieval(
    ranked_by_question: Mapping[str, Sequence[RankedResult]],
    gold_by_question: Mapping[str, frozenset[str]],
    gold_docs_by_question: Mapping[str, frozenset[str]],
) -> dict[str, float]:
    """Aggregate A1 metrics across questions (question as unit)."""
    questions = tuple(sorted(ranked_by_question))
    if not questions:
        return {}
    return {
        "document_recall_at_5": sum(
            document_recall_at_k(ranked_by_question[q], gold_docs_by_question[q], k=5)
            for q in questions
        ) / len(questions),
        "all_required_evidence_recall_at_20": sum(
            all_required_evidence_recall(ranked_by_question[q], gold_by_question[q], k=20)
            for q in questions
        ) / len(questions),
        "mrr": sum(mrr(ranked_by_question[q], gold_by_question[q]) for q in questions) / len(questions),
        "ndcg_at_20": sum(
            ndcg_at_k(ranked_by_question[q], gold_by_question[q], k=20)
            for q in questions
        ) / len(questions),
        "set_precision_at_20": sum(
            set_precision(ranked_by_question[q], gold_by_question[q], k=20)
            for q in questions
        ) / len(questions),
        "redundancy_at_20": sum(
            redundancy(ranked_by_question[q], k=20) for q in questions
        ) / len(questions),
        "question_count": len(questions),
    }
