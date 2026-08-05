from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.temporal_eval.baselines import (
    run_b1_bm25,
    run_b2_hybrid,
    run_b3_source_time_filter,
    run_b4_valid_time_filter,
    run_b5_temporal_contradiction,
)
from ecoquant.research.temporal_eval.questions import build_temporal_questions
from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/sec"


@pytest.fixture(scope="module")
def data():
    bundle = load_companyfacts(CACHE, tickers=("AAPL", "MSFT", "KO"))
    questions = build_temporal_questions(bundle)
    return bundle, questions


def _check_ranked(predictions, n_questions) -> None:
    assert len(predictions) == n_questions
    for qid, facts in predictions.items():
        assert facts  # non-empty per question


def test_b1_returns_ranked(data) -> None:
    bundle, questions = data
    preds = run_b1_bm25(bundle, questions[:20])
    _check_ranked(preds, 20)


def test_b2_hybrid_returns_ranked(data) -> None:
    bundle, questions = data
    preds = run_b2_hybrid(bundle, questions[:20])
    _check_ranked(preds, 20)


def test_b3_source_time_filter_returns_ranked(data) -> None:
    bundle, questions = data
    preds = run_b3_source_time_filter(bundle, questions[:20])
    _check_ranked(preds, 20)


def test_b4_valid_time_filter_returns_ranked(data) -> None:
    bundle, questions = data
    preds = run_b4_valid_time_filter(bundle, questions[:20])
    _check_ranked(preds, 20)


def test_b5_temporal_contradiction_returns_ranked(data) -> None:
    bundle, questions = data
    preds = run_b5_temporal_contradiction(bundle, questions[:20])
    _check_ranked(preds, 20)


def test_all_methods_same_question_ids(data) -> None:
    bundle, questions = data
    qids = [q.question_id for q in questions[:20]]
    p1 = run_b1_bm25(bundle, questions[:20])
    p5 = run_b5_temporal_contradiction(bundle, questions[:20])
    assert set(p1) == set(qids) == set(p5)
