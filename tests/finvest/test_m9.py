from __future__ import annotations

from pathlib import Path

import pytest

from finvest.integration.evidence_package import build_evidence_package
from finvest.paper.auto_tables import artifact_checklist, result_table_latex, result_table_markdown
from finvest.release.validate import validate_release

ROOT = Path(__file__).resolve().parents[2]


def test_evidence_package_boundary_holds() -> None:
    package = build_evidence_package(
        question="What is AAPL FCFF for FY2024?",
        answer="8.8 billion",
        evidence_set=("ev-ocf", "ev-capex"),
        requirement_coverage={"ocf": True, "capex": True},
        calculation_program={"operation": "subtract", "result": 8.8e9},
        temporal_status={"valid": True},
        version_status={"latest": "10-K"},
        conflict_status={"conflicts": []},
        sufficiency_status="SUPPORTED",
        calibrated_risk=0.05,
        review_route="auto",
    )
    assert package.validate_boundary() == []  # no spread/loan/transfer/trade
    assert package.attestation is not None  # signed on SUPPORTED
    assert "spread_bps" not in package.attestation


def test_evidence_package_no_attestation_on_insufficient() -> None:
    package = build_evidence_package(
        question="q", answer=None, evidence_set=(),
        requirement_coverage={}, calculation_program=None,
        temporal_status={}, version_status={}, conflict_status={},
        sufficiency_status="INSUFFICIENT", calibrated_risk=0.9, review_route="review",
    )
    assert package.attestation is None


def test_result_table_markdown() -> None:
    table = result_table_markdown(
        [{"method": "bm25", "recall": 0.5}], columns=["method", "recall"], title="A1",
    )
    assert "bm25" in table and "recall" in table


def test_result_table_latex() -> None:
    table = result_table_latex(
        [{"method": "bm25", "recall": 0.5}], columns=["method", "recall"],
        caption="A1", label="tab:a1",
    )
    assert "\\begin{table}" in table and "\\label{tab:a1}" in table


def test_artifact_checklist() -> None:
    missing = artifact_checklist(ROOT / "research/results")
    assert missing == []  # all E0-E8 artifacts committed


def test_release_validate_runs() -> None:
    result = validate_release()
    assert "artifacts_present" in result
    assert "feature_builders_leak_free" in result
    assert "paper_tables_generate" in result
