from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.table_eval.griqa import load_griqa_quant

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/griqa"

FUNCTIONS = {
    "average", "sum", "increase_difference", "reduction_difference",
    "increase_percentage", "reduction_percentage",
}


@pytest.fixture(scope="module")
def bundle():
    return load_griqa_quant(CACHE)


def test_quant_bundle_counts(bundle) -> None:
    assert len(bundle.questions) == 266
    assert len(bundle.tables) == 27


def test_question_fields(bundle) -> None:
    for q in bundle.questions:
        assert q.question_id
        assert q.question
        assert isinstance(q.value, float)
        assert q.fn_name in FUNCTIONS
        assert q.row_indices and q.col_indices


def test_question_cell_coordinates_are_interpretable(bundle) -> None:
    """row/col indices are either aligned pairs or a grid region.

    Most questions use aligned (row_i, col_i) pairs. A few (e.g. a sum over a
    multi-row x multi-col block) have unequal lengths — those are interpreted as
    a grid region (all row x col combinations).
    """
    for q in bundle.questions:
        if len(q.row_indices) == len(q.col_indices):
            assert q.row_indices and q.col_indices  # aligned pairs
        else:
            # grid region: >1 row and >1 col
            assert len(q.row_indices) > 1 and len(q.col_indices) > 1


def test_table_text_serialization(bundle) -> None:
    for t in bundle.tables:
        assert t.table_id
        assert t.text  # non-empty
        assert t.rows


def test_tables_are_joinable_to_questions(bundle) -> None:
    """Every question's (company, page, table) resolves to a known table."""
    table_ids = {t.table_id for t in bundle.tables}
    for q in bundle.questions:
        expected = f"{q.company}_{q.page}_{q.table_nbr}"
        assert expected in table_ids, f"question {q.question_id} table {expected} missing"
