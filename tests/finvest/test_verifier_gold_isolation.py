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

import ast
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


def test_verify_never_reads_calculation_program() -> None:
    """P0-9: the production verifier must not consume case['calculation_program'].

    That field lives beside the hidden answer in the sealed benchmark payload;
    if the verifier read the operation from it, the executability check would
    be oracle-assisted — the model must predict SUBTRACT/OCF/CAPEX from the
    question text itself.
    """
    run_py = Path(__file__).resolve().parents[2] / "experiments/a11_retrieval/run.py"
    tree = ast.parse(run_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_verify":
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "get"
                ):
                    args = [
                        a for a in sub.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    ]
                    if any(a.value == "calculation_program" for a in args):
                        raise AssertionError(
                            "production verifier must never read calculation_program "
                            f"(P0-9), found at run.py:{sub.lineno}"
                        )
                if isinstance(sub, ast.Subscript):
                    if (
                        isinstance(sub.slice, ast.Constant)
                        and sub.slice.value == "calculation_program"
                    ):
                        raise AssertionError(
                            "production verifier must never read calculation_program "
                            f"(P0-9), found at run.py:{sub.lineno}"
                        )
            return
    raise AssertionError("_verify function not found in run.py")


def test_production_path_never_reads_gold_adjacent_fields() -> None:
    """P0-9 Gate 0: production-only functions must not read gold-adjacent fields.

    The sealed payload fields answer_type / sufficiency_label / decision_label /
    requirement_graph are benchmark annotations, NOT production inputs (a real
    user provides only the question + issuer + cutoffs). The production
    functions (_verify, build_query) must not consume them. The S4 oracle and
    the evaluator are excluded — they legitimately touch gold (flagged).
    """
    run_py = Path(__file__).resolve().parents[2] / "experiments/a11_retrieval/run.py"
    tree = ast.parse(run_py.read_text(encoding="utf-8"))
    forbidden = {
        "requirement_graph", "answer_type", "sufficiency_label", "decision_label",
    }
    targets = {"_verify", "build_query"}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "get"
                ):
                    for a in sub.args:
                        if isinstance(a, ast.Constant) and a.value in forbidden:
                            found.append((node.name, f".get({a.value!r})", sub.lineno))
                if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Constant):
                    if sub.slice.value in forbidden:
                        found.append((node.name, f"[{sub.slice.value!r}]", sub.lineno))
    assert not found, f"production path reads gold-adjacent fields (P0-9): {found}"


def test_verify_decision_invariant_to_calculation_program_mutation() -> None:
    """P0-9 Gate 0 core test: mutating case['calculation_program'] must NOT change
    the production decision or the induced program.

    The executability check must derive its program from the question text
    (P0-9), so deleting the field or changing its operation leaves the decision
    identical. This is the exact invariant the source audit demanded: '改变 /
    删除 calculation_program → production prediction 不应该因此改变'.
    """
    from datetime import date

    from experiments.a11_retrieval.run import _verify
    from finvest.benchmark.schemas import EvidenceItem, VersionRelation
    from finvest.verification.numerical import verify_calculation
    from finvest.verification.temporal_version import verify_joint_temporal

    items = (
        EvidenceItem(
            evidence_id="e-ocf", document_id="AAPL-10-K-2023-09-30",
            document_version="10-K", filing_date=date(2023, 11, 1),
            valid_to=date(2023, 9, 30),
            text_span=(
                "NetCashProvidedByUsedInOperatingActivities 110543000000 USD "
                "2022-09-25 2023-09-30 2023-11-01 10-K ACC1"
            ),
            concept="NetCashProvidedByUsedInOperatingActivities",
        ),
        EvidenceItem(
            evidence_id="e-capex", document_id="AAPL-10-K-2023-09-30",
            document_version="10-K", filing_date=date(2023, 11, 1),
            valid_to=date(2023, 9, 30),
            text_span=(
                "PaymentsToAcquirePropertyPlantAndEquipment 10959000000 USD "
                "2022-09-25 2023-09-30 2023-11-01 10-K ACC1"
            ),
            concept="PaymentsToAcquirePropertyPlantAndEquipment",
        ),
    )
    base = {
        "question": (
            "What is AAPL operating cash flow minus capital expenditure for the "
            "fiscal period ending 2023-09-30?"
        ),
        "source_cutoff": "2023-11-01T00:00:00Z",
        "target_period_end": "2023-09-30",
        "target_fiscal_year": "FY2023",
        "version_relations": [],
    }
    # Three payload variants: field present with a WRONG operation, field
    # present with the "correct" operation, field absent entirely.
    variants = [
        {**base, "calculation_program": {"operation": "sum"}},
        {**base, "calculation_program": {"operation": "subtract"}},
        base,
    ]
    results = [
        _verify(items, case, None, verify_joint_temporal, verify_calculation,
                EvidenceItem, VersionRelation)
        for case in variants
    ]
    # The induced program must be identical across all variants (question-driven).
    for r in results[1:]:
        assert r["numerical"]["induced_program"] == results[0]["numerical"]["induced_program"]
    # The decision and numerical verdict must be identical too.
    for r in results[1:]:
        assert r["joint_valid"] == results[0]["joint_valid"]
        assert r["numerical"]["verification_state"] == results[0]["numerical"]["verification_state"]
    # Sanity: the induced program really is subtract with OCF + capex inputs.
    induced = results[0]["numerical"]["induced_program"]
    assert induced["operation"] == "subtract"
    assert "NetCashProvidedByUsedInOperatingActivities" in induced["required_metrics"]
    assert "PaymentsToAcquirePropertyPlantAndEquipment" in induced["required_metrics"]


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
