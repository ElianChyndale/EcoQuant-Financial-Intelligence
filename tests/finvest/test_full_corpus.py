from __future__ import annotations

from pathlib import Path

import pytest

from finvest.fixtures.full_10k_fixture import FIXTURE_DIR as FULL_10K_FIXTURE_DIR
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
    # Committed full 10-K HTML fixture (2 documents) — runs in CI, no cache.
    return build_full_corpus(CACHE, corpus_dir=FULL_10K_FIXTURE_DIR)


def test_full_corpus_builds(corpus) -> None:
    assert len(corpus.units) > 5  # the synthetic fixture has paragraphs+tables
    assert len(corpus.documents) >= 2
    for doc in corpus.documents:
        assert doc in corpus.by_document


def test_bm25_retrieves_relevant_units(corpus) -> None:
    results = bm25_retrieve(corpus, "total assets fiscal 2024", top_k=20)
    assert len(results) == min(20, len(corpus.units))
    assert [r.rank for r in results] == list(range(1, len(results) + 1))
    # Sorted by descending score.
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


DENSE_MODEL_DIR = ROOT / "research/cache/models/all-MiniLM-L6-v2"


@pytest.mark.skipif(
    not DENSE_MODEL_DIR.exists(),
    reason="dense embedding model cache absent (gitignored)",
)
def test_dense_retrieves(corpus) -> None:
    results = dense_retrieve(corpus, "net income fiscal 2025", top_k=10)
    assert len(results) == min(10, len(corpus.units))


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
