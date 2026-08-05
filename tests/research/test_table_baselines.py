from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.table_eval.baselines import run_b3_table_only, run_b7_long_context, run_proposed
from ecoquant.research.table_eval.griqa import load_griqa_quant

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/griqa"


@pytest.fixture(scope="module")
def bundle():
    return load_griqa_quant(CACHE)


def test_b3_returns_prediction_per_question(bundle) -> None:
    predictions = run_b3_table_only(bundle)
    assert len(predictions) == 266
    for qid, value in predictions.items():
        assert value is None or isinstance(value, float)


def test_b7_returns_prediction_per_question(bundle) -> None:
    predictions = run_b7_long_context(bundle)
    assert len(predictions) == 266
    for qid, value in predictions.items():
        assert value is None or isinstance(value, float)


def test_proposed_returns_prediction_per_question(bundle) -> None:
    predictions = run_proposed(bundle)
    assert len(predictions) == 266
    for qid, value in predictions.items():
        assert value is None or isinstance(value, float)


def test_b7_has_high_answer_coverage(bundle) -> None:
    """Long-context (gold cells known) should answer most questions.

    Even with the gold table, some questions are unanswerable because the gold
    cells are non-parseable (dashes, ranges) or the required values span
    non-numeric regions. 194/266 ≈ 73% is the honest coverage.
    """
    predictions = run_b7_long_context(bundle)
    answered = sum(1 for v in predictions.values() if v is not None)
    assert answered >= 180  # >67% answered (observed 194/266)
