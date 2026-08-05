"""Deterministic calculation for GRI-QA quant questions with unit handling.

The six GRI-QA functions are implemented exactly (matching the paper's
``QuantitativeResponseGenerator`` semantics):

- ``average``: mean of values.
- ``sum``: sum of values.
- ``increase_difference``: newer - older.
- ``reduction_difference``: previous - current (positive = reduction).
- ``increase_percentage``: (newer - older) / older * 100.
- ``reduction_percentage``: (previous - current) / previous * 100.

Cell parsing handles the real-table formats observed in GRI-QA: plain numbers,
trailing units (``m3``, ``Mt CO2e``), percentages (``63%``), parenthetical
previous-year values (``389 (381)``), and ``-``/``n/a`` for missing cells.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

FUNCTIONS = {
    "average", "sum", "increase_difference", "reduction_difference",
    "increase_percentage", "reduction_percentage",
}

_NUMBER_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")
_NEGATIVE_PAREN_RE = re.compile(r"\((-?\d+(?:[.,]\d+)?)\)")


def parse_cell(cell: str) -> float | None:
    """Parse a table cell into a number, or None if non-numeric / missing.

    Rules:
    - ``-``, empty, ``;``, ``n/a`` → None (missing).
    - ``(x)`` → -x (negative in parentheses, common in financial tables).
    - ``389 (381)`` → 389 (primary value; parenthetical is ignored).
    - ``63%``, ``432730 m3``, ``355 Mt CO2e`` → numeric prefix.
    """
    text = cell.strip()
    if not text or text in {"-", ";", "n/a", "N/A", "NA"}:
        return None
    # Parenthetical negative, e.g. "(123)"
    if text.startswith("(") and text.endswith(")"):
        match = _NUMBER_RE.search(text[1:-1])
        if match:
            return -float(match.group(1).replace(",", "."))
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def extract_cells(
    table: Sequence[Sequence[str]],
    row_indices: Sequence[int],
    col_indices: Sequence[int],
) -> list[float]:
    """Extract numeric cells from a table given row/col indices.

    Semantics follow GRI-QA's ``row indices`` / ``col indices`` fields:

    - Aligned pairs (equal length, varying values): zip(row, col).
    - Column span (rows vary, col constant): one column across many rows.
    - Row span (col varies, row constant): one row across many columns.
    - Grid region (both vary, unequal length): cross product (all row x col).
    """
    rows = list(row_indices)
    cols = list(col_indices)
    row_constant = len(set(rows)) == 1
    col_constant = len(set(cols)) == 1
    if len(rows) == len(cols) and not (row_constant or col_constant):
        pairs = list(zip(rows, cols))
    elif col_constant:
        pairs = [(r, cols[0]) for r in rows]
    elif row_constant:
        pairs = [(rows[0], c) for c in cols]
    else:
        pairs = [(r, c) for r in rows for c in cols]

    cells: list[float] = []
    for row_idx, col_idx in pairs:
        if row_idx < 0 or col_idx < 0:
            continue
        if row_idx >= len(table) or col_idx >= len(table[row_idx]):
            continue
        value = parse_cell(table[row_idx][col_idx])
        if value is not None:
            cells.append(value)
    return cells


def calculate(fn_name: str, values: Sequence[float]) -> float:
    """Apply one of the six GRI-QA deterministic functions."""
    if fn_name not in FUNCTIONS:
        raise ValueError(f"unknown GRI-QA function: {fn_name}")
    if not values:
        raise ValueError(f"{fn_name} requires at least one value")
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        raise ValueError(f"{fn_name} has no finite values")

    if fn_name == "average":
        return sum(finite) / len(finite)
    if fn_name == "sum":
        return sum(finite)
    if fn_name == "increase_difference":
        return finite[-1] - finite[0]
    if fn_name == "reduction_difference":
        return finite[0] - finite[-1]
    if fn_name == "increase_percentage":
        if finite[0] == 0:
            raise ValueError("increase_percentage divide by zero")
        return (finite[-1] - finite[0]) / abs(finite[0]) * 100.0
    if fn_name == "reduction_percentage":
        if finite[0] == 0:
            raise ValueError("reduction_percentage divide by zero")
        return (finite[0] - finite[-1]) / abs(finite[0]) * 100.0
    raise ValueError(f"unhandled function: {fn_name}")
