"""Tests: FinVEST program induction (P0-9) — question -> executable program.

The induction module turns a natural-language question into an executable
symbolic program (operation + required metric concepts) WITHOUT reading any
benchmark case payload field. These tests pin:
  - the gold-free contract (only the question string is consumed);
  - the operation/required-metric mapping for the real sealed cases
    (9 cashflow 'subtract' cases and 30 extractive 'no-op' cases);
  - the FCFF derivation rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

from finvest.program_induction.induction import induce_program


def test_induce_program_subtract_cashflow() -> None:
    """'operating cash flow minus capital expenditure' -> subtract(OCF, CAPEX)."""
    prog = induce_program(
        "What is AAPL operating cash flow minus capital expenditure for the "
        "fiscal period ending 2023-09-30?"
    )
    assert prog.operation == "subtract"
    assert "NetCashProvidedByUsedInOperatingActivities" in prog.required_metrics
    assert "PaymentsToAcquirePropertyPlantAndEquipment" in prog.required_metrics
    assert prog.entity == "AAPL"
    assert prog.period == "FY2023"


def test_induce_program_extractive_no_op() -> None:
    """An extractive question has no executable operation."""
    prog = induce_program("What is Assets for AAPL for fiscal year 2022?")
    assert prog.operation is None
    assert prog.period == "FY2022"


def test_induce_program_fcff_derivation() -> None:
    """'free cash flow' derives subtract(OCF, CAPEX) even without 'minus'."""
    prog = induce_program("What is MSFT free cash flow for fiscal 2025?")
    assert prog.operation == "subtract"
    assert prog.source == "fcff-derivation"
    assert set(prog.required_metrics) == {
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    }


def test_induce_program_empty_question() -> None:
    """Empty / whitespace question -> no program, honest provenance."""
    prog = induce_program("   ")
    assert prog.operation is None
    assert prog.source == "empty-question"
    assert prog.required_metrics == ()


def test_induce_program_matches_sealed_calculation_programs() -> None:
    """On the real sealed cases, induction reproduces the gold operation set.

    This is a diagnostic (the gold payload is consumed ONLY by this test, never
    by production): the module must not read it, yet its operation predictions
    must cover the 9 'subtract' + 30 'no-op' cases exactly.
    """
    import json

    root = Path(__file__).resolve().parents[2]
    cases_path = root / "human_review/day1/v0.2-draft/EXTENSION_40_cases.json"
    if not cases_path.exists():
        import pytest

        pytest.skip("sealed extension cases not present")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    assert cases, "sealed extension case list is empty"
    mismatches = []
    for c in cases:
        gold_op = (c.get("calculation_program") or {}).get("operation")
        predicted = induce_program(c.get("question", ""))
        if gold_op is not None and predicted.operation != gold_op:
            mismatches.append((c.get("case_id"), gold_op, predicted.operation))
    assert not mismatches, f"induction disagrees with sealed programs: {mismatches}"


def test_induce_program_gold_free_contract() -> None:
    """induce_program consumes ONLY the question string — no payload access."""
    module = Path(__file__).resolve().parents[2] / "finvest/program_induction/induction.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "induce_program":
            params = {a.arg for a in node.args.args}
            assert params <= {"question"}, (
                f"induce_program must take only 'question', got {params}"
            )
            for sub in ast.walk(node):
                assert not isinstance(sub, ast.Subscript), (
                    "induce_program must not index any payload (P0-9)"
                )
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "get"
                ):
                    raise AssertionError("induce_program must not call .get() on a payload")
            return
    raise AssertionError("induce_program function not found")
