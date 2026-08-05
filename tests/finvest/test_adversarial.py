from __future__ import annotations

import pytest

from finvest.verification.adversarial import (
    ERROR_TYPES,
    build_adversarial_cases,
    evaluate_adversarial,
)


@pytest.fixture
def base() -> tuple[tuple[str, str], ...]:
    return (
        ("What is Apple revenue for FY2024?", "Apple revenue was 391.0 billion in fiscal 2024."),
        ("What is Microsoft net income for FY2025?", "Microsoft net income was 88.0 billion in fiscal 2025."),
    )


def test_build_scales_to_1000() -> None:
    """125 bases x 8 conditions = 1,000 cases (A5 target)."""
    base = tuple(
        (f"question {i} revenue FY2024?", f"Company {i} revenue was 100.0 billion in fiscal 2024.")
        for i in range(125)
    )
    cases = build_adversarial_cases(base_questions=base)
    assert len(cases) == 125 * 8
    assert len(cases) >= 1000


def test_build_scales_with_base(base) -> None:
    cases = build_adversarial_cases(base_questions=base)
    # 2 bases x 8 conditions = 16
    assert len(cases) == 16
    states = {c.gold_state for c in cases}
    assert "SUPPORTED" in states
    assert "wrong_number" in states
    assert "conflicting_evidence" in states


def test_all_error_types_represented(base) -> None:
    cases = build_adversarial_cases(base_questions=base)
    error_types = {c.error_type for c in cases if c.error_type}
    # Subset of ERROR_TYPES that the generator emits for a simple base.
    assert error_types <= set(ERROR_TYPES)
    assert "wrong_number" in error_types
    assert "wrong_year" in error_types


def test_evaluate_adversarial_metrics(base) -> None:
    cases = build_adversarial_cases(base_questions=base)

    def number_grounded_verifier(claim: str, evidence: tuple[str, ...]) -> str:
        """E4-style: SUPPORTED only if every claim number is in the evidence."""
        import re

        claim_numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", claim)]
        evidence_text = " ".join(evidence)
        if all(str(int(n)) in evidence_text or f"{n}" in evidence_text for n in claim_numbers):
            return "SUPPORTED"
        return "INSUFFICIENT_EVIDENCE"

    metrics = evaluate_adversarial(number_grounded_verifier, cases)
    assert 0.0 <= metrics["false_support_rate"] <= 1.0
    assert metrics["total_cases"] == len(cases)
    assert "per_error_type_f1" in metrics
    # wrong_number cases have a different number in evidence -> not grounded.
    wrong_number = [c for c in cases if c.error_type == "wrong_number"]
    assert wrong_number
    assert all(
        number_grounded_verifier(c.claim, c.cited_evidence) != "SUPPORTED"
        for c in wrong_number
    )


def test_naive_verifier_has_high_false_support(base) -> None:
    cases = build_adversarial_cases(base_questions=base)

    def naive_verifier(claim: str, evidence: tuple[str, ...]) -> str:
        return "SUPPORTED"  # always accepts

    metrics = evaluate_adversarial(naive_verifier, cases)
    assert metrics["false_support_rate"] == 1.0
