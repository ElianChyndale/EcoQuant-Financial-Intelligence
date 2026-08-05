from __future__ import annotations

import pytest

from ecoquant.research.verification_eval.verifier import ClaimInput, verify_claim


def test_supported_claim() -> None:
    r = verify_claim(ClaimInput(
        claim_text="AAPL revenue was 391.0 billion in 2024",
        numbers=[391.0],
        cited_evidence=["Revenue 391.0 billion in fiscal 2024"],
        expected_year="2024",
        expected_unit=None,
        expected_scale="billion",
        expected_value=None,
    ))
    assert r.state == "SUPPORTED"
    assert r.layer_results["number_in_evidence"] is True
    assert r.layer_results["year_consistent"] is True


def test_unsupported_number_rejected() -> None:
    r = verify_claim(ClaimInput(
        claim_text="revenue was 999 billion",
        numbers=[999.0],
        cited_evidence=["Revenue 391.0 billion"],
        expected_year="2024",
        expected_unit=None,
        expected_scale="billion",
        expected_value=None,
    ))
    assert r.state == "INSUFFICIENT_EVIDENCE"
    assert r.layer_results["number_in_evidence"] is False


def test_conflicting_evidence_detected() -> None:
    r = verify_claim(ClaimInput(
        claim_text="Assets = 39.5 billion",
        numbers=[39.5],
        cited_evidence=["Assets 39.5 billion", "Assets 36.2 billion (restated)"],
        expected_year=None,
        expected_unit=None,
        expected_scale="billion",
        expected_value=None,
    ))
    assert r.state == "CONFLICTING_EVIDENCE"
    assert r.layer_results["no_conflict"] is False


def test_missing_citation_review() -> None:
    r = verify_claim(ClaimInput(
        claim_text="revenue 391 billion",
        numbers=[391.0],
        cited_evidence=[],
        expected_year=None,
        expected_unit=None,
        expected_scale="billion",
        expected_value=None,
    ))
    assert r.state == "REVIEW_REQUIRED"
    assert r.layer_results["citation_present"] is False


def test_year_inconsistent_review() -> None:
    r = verify_claim(ClaimInput(
        claim_text="revenue 391 billion in 2023",
        numbers=[391.0],
        cited_evidence=["Revenue 391.0 billion in fiscal 2024"],
        expected_year="2023",
        expected_unit=None,
        expected_scale="billion",
        expected_value=None,
    ))
    assert r.state == "REVIEW_REQUIRED"
    assert r.layer_results["year_consistent"] is False


def test_calculation_reproducible() -> None:
    r = verify_claim(ClaimInput(
        claim_text="average of 4710 and 4710 is 4710",
        numbers=[4710.0, 4710.0],
        cited_evidence=["2022: 4710", "2023: 4710"],
        expected_year=None,
        expected_unit=None,
        expected_scale=None,
        expected_value=4710.0,
    ))
    assert r.state == "SUPPORTED"
    assert r.layer_results["calculation_reproducible"] is True
