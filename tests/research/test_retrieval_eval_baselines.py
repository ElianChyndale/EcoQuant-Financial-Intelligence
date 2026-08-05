from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.datasets.financebench import load_financebench
from ecoquant.research.retrieval_eval.baselines import run_baselines
from ecoquant.research.retrieval_eval.corpora import build_financebench_corpus

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/financebench"


@pytest.fixture(scope="module")
def data():
    bundle = load_financebench(
        questions_path=CACHE / "financebench_open_source.jsonl",
        docs_path=CACHE / "financebench_document_information.jsonl",
    )
    corpus, catalog, gold = build_financebench_corpus(bundle)
    return bundle.public_cases, corpus, catalog, gold


def test_baselines_cover_expected_methods(data) -> None:
    queries, corpus, catalog, gold = data
    results = run_baselines(corpus, queries)
    assert set(results) == {"bm25", "tfidf", "lsa", "dense", "hybrid_rrf", "long_context"}


def test_every_method_returns_ranked_results(data) -> None:
    queries, corpus, catalog, gold = data
    results = run_baselines(corpus, queries)
    for method, by_question in results.items():
        assert len(by_question) == 150
        for question_id, ranked in by_question.items():
            assert 1 <= len(ranked) <= 5
            assert [r.rank for r in ranked] == list(range(1, len(ranked) + 1))


def test_results_are_deterministic(data) -> None:
    queries, corpus, catalog, gold = data
    first = run_baselines(corpus, queries)
    second = run_baselines(corpus, queries)
    assert first == second
