from __future__ import annotations

import pytest

from ecoquant.research.table_eval.calculate import calculate, extract_cells, parse_cell


def test_parse_cell_plain_number() -> None:
    assert parse_cell("4710") == 4710.0
    assert parse_cell("29.09") == 29.09
    assert parse_cell("1234.5") == 1234.5


def test_parse_cell_with_units() -> None:
    assert parse_cell("432730 m3") == 432730.0
    assert parse_cell("355 Mt CO2e") == 355.0
    assert parse_cell("10 m3/Headcount") == 10.0


def test_parse_cell_parenthetical() -> None:
    # "389 (381)" — primary value 389
    assert parse_cell("389 (381)") == 389.0


def test_parse_cell_missing() -> None:
    assert parse_cell("-") is None
    assert parse_cell("") is None
    assert parse_cell(";") is None


def test_parse_cell_percent() -> None:
    assert parse_cell("63%") == 63.0
    assert parse_cell("-10%") == -10.0


def test_parse_cell_non_numeric() -> None:
    assert parse_cell("n/a") is None
    assert parse_cell("Energy consumption") is None


@pytest.mark.parametrize("fn,values,expected", [
    ("average", [4710.0, 4710.0], 4710.0),
    ("sum", [100.0, 200.0, 300.0], 600.0),
    ("increase_difference", [100.0, 120.0], 20.0),
    ("reduction_difference", [120.0, 100.0], 20.0),
    ("increase_percentage", [100.0, 120.0], 20.0),
    ("reduction_percentage", [120.0, 100.0], 16.666666666666664),
])
def test_calculate_functions(fn, values, expected) -> None:
    assert calculate(fn, values) == pytest.approx(expected)


def test_calculate_subtract() -> None:
    """FinVEST cashflow-proxy cases use operation='subtract' (OCF - capex).

    Semantics: first value minus the remaining values (matches the derived
    cash-flow proxy where OCF is the first input). Without this, the real
    A11 cases can never produce a SUPPORTED numerical verification.
    """
    assert calculate("subtract", [100.0, 30.0]) == 70.0
    assert calculate("subtract", [100.0, 30.0, 10.0]) == 60.0


def test_calculate_unknown_function() -> None:
    with pytest.raises(ValueError):
        calculate("unknown", [1.0])


def test_extract_cells_aligned_pairs() -> None:
    table = [
        ("header", "2022", "2023"),
        ("Total waste", "4300", "5120"),
    ]
    cells = extract_cells(table, [1, 1], [1, 2])
    assert cells == [4300.0, 5120.0]


def test_extract_cells_column_span() -> None:
    """Rows vary, col constant → one column across many rows (GRI-QA pattern)."""
    table = [
        ("h", "2022", "2023"),
        ("a", "1", "2"),
        ("b", "3", "4"),
    ]
    cells = extract_cells(table, [1, 2], [2, 2])
    assert cells == [2.0, 4.0]


def test_extract_cells_grid_region_unequal() -> None:
    """Both vary, unequal length → cross product (all row x col)."""
    table = [
        ("h", "2022", "2023"),
        ("a", "1", "2"),
        ("b", "3", "4"),
    ]
    # rows 1..2 x cols 1..2 => 1,2,3,4
    cells = extract_cells(table, [1, 2], [1, 2, 1, 2])
    assert cells == [1.0, 2.0, 1.0, 2.0, 3.0, 4.0, 3.0, 4.0]
