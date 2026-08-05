from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from ecoquant.research.temporal_eval.questions import build_temporal_questions
from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/sec"


@pytest.fixture(scope="module")
def bundle():
    return load_companyfacts(CACHE, tickers=("AAPL", "MSFT", "KO"))


@pytest.fixture(scope="module")
def questions(bundle):
    return build_temporal_questions(bundle)


def test_three_question_classes_present(questions) -> None:
    classes = Counter(q.question_class for q in questions)
    for required in ("old_vs_new", "amended_vs_original", "cross_period"):
        assert classes[required] >= 5, f"too few {required} questions: {classes[required]}"


def test_question_fields(questions) -> None:
    for q in questions:
        assert q.question_id
        assert q.question
        assert q.ticker
        assert q.concept
        assert isinstance(q.valid_at, date)
        assert isinstance(q.source_cutoff, date)
        assert q.gold_answer is not None
        assert q.gold_evidence_ids


def test_amended_questions_flag_contradiction(questions) -> None:
    amended = [q for q in questions if q.question_class == "amended_vs_original"]
    assert amended
    assert all(q.is_contradiction for q in amended)


def test_gold_answers_are_real_values(questions, bundle) -> None:
    """Every gold answer must match the actual fact its gold evidence cites."""
    facts_by_id = {fact.fact_id: fact for fact in bundle.facts}
    for q in questions:
        assert q.gold_evidence_ids  # non-empty
        for evidence_id in q.gold_evidence_ids:
            fact = facts_by_id[evidence_id]
            assert abs(fact.val - q.gold_answer) < 1e-6
            assert fact.ticker == q.ticker
            assert fact.concept == q.concept
