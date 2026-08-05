from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.verification_eval.benchmark import build_benchmark_cases

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cases():
    return build_benchmark_cases(ROOT)


def test_benchmark_has_supported_and_unsupported(cases) -> None:
    states = {case.gold_state for case in cases}
    assert "SUPPORTED" in states
    assert "INSUFFICIENT_EVIDENCE" in states


def test_benchmark_case_fields(cases) -> None:
    for case in cases:
        assert case.case_id
        assert case.claim_input.claim_text
        assert case.gold_state in ("SUPPORTED", "INSUFFICIENT_EVIDENCE")
        assert case.claim_input.numbers


def test_benchmark_has_reasonable_size(cases) -> None:
    assert len(cases) >= 40  # supported + unsupported across datasets


def test_unsupported_cases_have_wrong_numbers(cases) -> None:
    """Injected unsupported cases carry numbers NOT in the cited evidence."""
    for case in cases:
        if case.gold_state == "INSUFFICIENT_EVIDENCE":
            evidence = " ".join(case.claim_input.cited_evidence)
            assert all(
                f"{number:.1f}" not in evidence or f"{number:.0f}" not in evidence
                for number in case.claim_input.numbers
            ) or all(
                f"{number:.0f}" not in evidence for number in case.claim_input.numbers
            )
