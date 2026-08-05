from __future__ import annotations

from pathlib import Path

import pytest

from finvest.retrieval.full_corpus import build_full_corpus, bm25_retrieve, dense_retrieve
from finvest.retrieval.metrics import (
    all_required_evidence_recall,
    document_recall_at_k,
    evaluate_retrieval,
    mrr,
    ndcg_at_k,
    set_precision,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache"


@pytest.fixture(scope="module")
def corpus():
    return build_full_corpus(CACHE)


def test_full_corpus_builds(corpus) -> None:
    assert len(corpus.units) > 1000  # 6 full 10-Ks → many evidence units
    assert len(corpus.documents) >= 6
    for doc in corpus.documents:
        assert doc in corpus.by_document


def test_bm25_retrieves_relevant_units(corpus) -> None:
    results = bm25_retrieve(corpus, "Apple total revenue fiscal 2025", top_k=20)
    assert len(results) == 20
    assert [r.rank for r in results] == list(range(1, 21))
    # Sorted by descending score.
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_dense_retrieves(corpus) -> None:
    results = dense_retrieve(corpus, "Microsoft net income fiscal 2025", top_k=10)
    assert len(results) == 10


def test_metrics_basic() -> None:
    ranked = [
        type("R", (), {"evidence_id": "e1", "document_id": "doc1", "score": 1.0, "rank": 1})(),
        type("R", (), {"evidence_id": "e2", "document_id": "doc1", "score": 0.9, "rank": 2})(),
        type("R", (), {"evidence_id": "e3", "document_id": "doc2", "score": 0.8, "rank": 3})(),
    ]
    gold = frozenset({"e1", "e3"})
    assert all_required_evidence_recall(ranked, gold, k=3) == 1.0
    assert mrr(ranked, gold) == 1.0
    assert document_recall_at_k(ranked, frozenset({"doc1", "doc2"}), k=3) == 1.0
    assert set_precision(ranked, gold, k=3) == 2 / 3
    assert 0.0 < ndcg_at_k(ranked, gold, k=3) <= 1.0


def test_evaluate_retrieval_question_unit(corpus) -> None:
    """End-to-end: retrieve for 2 questions, evaluate with question as unit."""
    questions = {
        "q1": "Apple total net sales fiscal 2025",
        "q2": "Microsoft research and development expense fiscal 2025",
    }
    ranked_by_question = {
        qid: bm25_retrieve(corpus, question, top_k=20) for qid, question in questions.items()
    }
    # No gold available without annotation; evaluate structure only.
    gold = {qid: frozenset() for qid in questions}
    gold_docs = {qid: frozenset() for qid in questions}
    metrics = evaluate_retrieval(ranked_by_question, gold, gold_docs)
    assert metrics["question_count"] == 2
    assert "document_recall_at_5" in metrics
