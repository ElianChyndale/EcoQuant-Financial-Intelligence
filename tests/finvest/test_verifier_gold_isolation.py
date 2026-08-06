"""Tests: production verifier must be GOLD-FREE (P0-2).

The production verifier decides ANSWER/REVIEW/ABSTAIN from the EVIDENCE alone;
the hidden gold answer is consumed ONLY by the offline evaluator
(evaluate_correctness). If the verifier ever received the gold, the routing
decision would leak the target even with a leak-free corpus.

Assertions:
- _verify (production) signature has NO gold/expected_value parameters;
- the production path calls verify_calculation with expected_value=None;
- evaluate_correctness is the ONLY place gold is compared.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from experiments.a11_retrieval.run import (
    _verify,
    evaluate_correctness,
    load_gold,
    load_sealed_cases,
)


def _production_verifier_signature() -> inspect.Signature:
    return inspect.signature(_verify)


def test_verify_signature_has_no_gold() -> None:
    """The production verifier must not accept gold in any form."""
    params = _production_verifier_signature().parameters
    names = set(params)
    forbidden = {"gold", "gold_answer", "expected_value", "expected"}
    assert not (names & forbidden), f"production verifier leaks gold params: {names & forbidden}"


def test_verify_source_never_reads_gold_answer() -> None:
    """The _verify SOURCE must not access case['gold_answer']."""
    import ast

    module = Path(__file__).resolve().parents[2] / "experiments/a11_retrieval/run.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_verify":
            src = ast.get_source_segment(module.read_text(encoding="utf-8"), node)
            assert "gold_answer" not in src, "_verify source reads gold_answer"
            assert "expected_value=" not in src or "expected_value=None" in src, (
                "production verify must pass expected_value=None"
            )
            return
    raise AssertionError("_verify function not found in run.py")


def test_evaluate_correctness_uses_gold_only_there() -> None:
    """evaluate_correctness is the gold-comparison boundary."""
    case = {"gold_answer": {"value": 100.0, "unit": "USD"}}
    verifier = {"numerical": {"result": 100.0, "verification_state": "SUPPORTED"}}
    ev = evaluate_correctness("ANSWER", verifier, case, human_route="ANSWER")
    assert ev["bucket"] == "answer"
    assert ev["correct"] is True
    assert ev["gold_used"] is True


def test_denominator_audit_present() -> None:
    """A11 output must carry the full denominator audit (P0-1)."""
    # The last produced report (production or fixture) must have it.
    result_path = Path(__file__).resolve().parents[2] / "research/results/a11_two_stage.json"
    if not result_path.exists():
        import pytest

        pytest.skip("a11_two_stage.json not generated yet")
    out = json.loads(result_path.read_text(encoding="utf-8"))
    audit = out["denominator_audit"]
    for key in (
        "n_packages_total", "n_annotated", "n_eligible_for_evaluation",
        "n_excluded_no_sealed_case", "n_excluded_failed_present",
        "n_final_evaluated", "n_answerable_gold", "n_insufficient_gold",
    ):
        assert key in audit, f"missing denominator key {key}"
    # Invariant: final = annotated - excluded_no_sealed - excluded_failed.
    assert audit["n_final_evaluated"] == (
        audit["n_annotated"] - audit["n_excluded_no_sealed_case"] - audit["n_excluded_failed_present"]
    )
    assert audit["n_packages_total"] >= audit["n_annotated"]
