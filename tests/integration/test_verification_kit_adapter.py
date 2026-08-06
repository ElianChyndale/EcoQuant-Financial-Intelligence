"""Tests for the financial-systems-verification-kit adapter (Phase 5.2).

Skipped when the tool repo is not installed. Asserts:
- the dual-implementation check passes a correct OCF-CapEx case;
- mutation challenges are all expected to be REJECTED (verifier discrimination);
- the dual check flags a wrong value.
"""

from __future__ import annotations

import pytest

financial_systems_verification = pytest.importorskip("financial_systems_verification")

from integrations.verification_kit_adapter import (
    DualCheck,
    dual_check_ocf_capex,
    generate_mutation_challenges,
    mutation_report,
)


def test_dual_check_correct() -> None:
    """Correct OCF-CapEx passes the dual-implementation check."""
    result = dual_check_ocf_capex(118254000000.0, 9447000000.0, expected=108807000000.0)
    assert result.passed is True
    assert result.ecoquant_result == 108807000000.0
    assert float(result.kit_result) == 108807000000.0


def test_dual_check_flags_wrong_expected() -> None:
    """A wrong expected value fails the dual check."""
    result = dual_check_ocf_capex(118254000000.0, 9447000000.0, expected=99999999999.0)
    assert result.passed is False
    assert "mismatch" in result.reason


def test_mutations_all_expected_rejected() -> None:
    """Every mutation must be REJECTED by a correct verifier."""
    mutations = generate_mutation_challenges(
        operating_cash_flow=118254000000.0,
        capital_expenditure=9447000000.0,
        expected=108807000000.0,
    )
    # 8 families.
    assert len(mutations) == 8
    tags = {m["mutation"] for m in mutations}
    assert "wrong-sign" in tags
    assert "scale-x1000" in tags
    assert "usd-vs-millions" in tags
    assert "future-source" in tags
    # Every mutation must not pass a correct verifier (would_pass False).
    for m in mutations:
        assert m["expected_verdict"] == "REVIEW_REQUIRED"
        assert m["would_pass"] is False, f"{m['mutation']} would falsely pass"


def test_mutation_report_counts() -> None:
    mutations = generate_mutation_challenges(
        operating_cash_flow=100.0, capital_expenditure=20.0, expected=80.0,
    )
    report = mutation_report(mutations)
    assert report["total_mutations"] == 8
    assert report["false_pass_risk"] == 0  # all mutations correctly rejected
    assert report["rejected_by_correct_verifier"] == 8
