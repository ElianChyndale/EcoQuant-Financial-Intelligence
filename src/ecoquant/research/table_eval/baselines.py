"""E2 baselines: table-only retrieval, long-context, and proposed pipeline.

- ``run_b3_table_only``: BM25 retrieves the best table for the question; extract
  cells at gold row/col; deterministic calc. Tests whether *retrieval* alone is
  sufficient.
- ``run_b7_long_context``: all tables are given (no retrieval); extract cells at
  gold row/col from the gold table; deterministic calc. Upper bound on cell
  extraction + calculation when the right table is known.
- ``run_proposed``: BM25 retrieves top-k tables; unit normalization; deterministic
  calc on cells from the best-retrieved table that yields a finite answer.

All return {question_id: float | None}.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rank_bm25 import BM25Okapi

from .calculate import calculate, extract_cells, header_years_for
from .griqa import GriqaBundle, GriqaTable, TableQuestion


def _tokenize(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text.lower()).split()


def _table_index(tables: Sequence[GriqaTable]) -> tuple[BM25Okapi, list[GriqaTable]]:
    tokenized = [_tokenize(table.text) for table in tables]
    return BM25Okapi(tokenized), list(tables)


def _best_table(question: TableQuestion, index: BM25Okapi, tables: list[GriqaTable]) -> GriqaTable | None:
    scores = index.get_scores(_tokenize(question.question))
    best = max(range(len(tables)), key=lambda i: (scores[i], tables[i].table_id))
    return tables[best]


def _answer_from_table(question: TableQuestion, table: GriqaTable) -> float | None:
    """Extract cells at gold coordinates (year-ordered) and apply the function."""
    years = header_years_for(table.rows)
    cells = extract_cells(
        table.rows, question.row_indices, question.col_indices, header_years=years,
    )
    if not cells:
        return None
    try:
        return calculate(question.fn_name, cells)
    except (ValueError, ZeroDivisionError):
        return None


def run_b3_table_only(bundle: GriqaBundle, top_k: int = 1) -> dict[str, float | None]:
    """Table-only retrieval baseline: BM25 finds the table, then calc."""
    index, tables = _table_index(bundle.tables)
    predictions: dict[str, float | None] = {}
    for question in bundle.questions:
        table = _best_table(question, index, tables)
        if table is None:
            predictions[question.question_id] = None
            continue
        predictions[question.question_id] = _answer_from_table(question, table)
    return predictions


def run_b7_long_context(bundle: GriqaBundle) -> dict[str, float | None]:
    """Long-context baseline: all tables given; use the gold table's cells."""
    tables_by_id = {table.table_id: table for table in bundle.tables}
    predictions: dict[str, float | None] = {}
    for question in bundle.questions:
        table_id = f"{question.company}_{question.page}_{question.table_nbr}"
        table = tables_by_id.get(table_id)
        if table is None:
            predictions[question.question_id] = None
            continue
        predictions[question.question_id] = _answer_from_table(question, table)
    return predictions


def run_proposed(bundle: GriqaBundle, top_k: int = 3) -> dict[str, float | None]:
    """Proposed pipeline: retrieval + unit normalization + deterministic calc."""
    index, tables = _table_index(bundle.tables)
    predictions: dict[str, float | None] = {}
    for question in bundle.questions:
        scores = index.get_scores(_tokenize(question.question))
        ranked = sorted(range(len(tables)), key=lambda i: (-scores[i], tables[i].table_id))[:top_k]
        answer: float | None = None
        for table_idx in ranked:
            answer = _answer_from_table(question, tables[table_idx])
            if answer is not None:
                break
        predictions[question.question_id] = answer
    return predictions
