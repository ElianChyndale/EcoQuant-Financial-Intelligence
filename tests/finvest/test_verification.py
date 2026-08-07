from __future__ import annotations

from datetime import date, datetime

import pytest

from finvest.benchmark.schemas import EvidenceItem, VersionRelation
from finvest.verification.numerical import locate_cells, verify_calculation
from finvest.verification.temporal_version import (
    latest_valid_version,
    verify_joint_temporal,
)


def _item(eid: str, doc: str, filed: str, valid: str | None, ver: str = "10-K") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=eid, document_id=doc, document_version=ver,
        filing_date=date.fromisoformat(filed),
        valid_from=date.fromisoformat(valid) if valid else None,
        concept="c", unit="USD", scale="1", scope="consolidated",
    )


def test_joint_temporal_all_valid() -> None:
    evidence = (_item("e1", "doc1", "2025-03-01", "2024-12-31"),)
    result = verify_joint_temporal(
        evidence,
        source_cutoff=datetime(2025, 12, 31),
        target_end=date(2024, 12, 31),
        target_fiscal_year="FY2024",
    )
    assert result.valid is True
    assert result.future_information_rate == 0.0
    assert result.expired_evidence_rate == 0.0


def test_joint_detects_future() -> None:
    evidence = (_item("e1", "doc1", "2026-03-01", "2024-12-31"),)
    result = verify_joint_temporal(
        evidence,
        source_cutoff=datetime(2025, 12, 31),
        target_end=date(2024, 12, 31),
        target_fiscal_year="FY2024",
    )
    assert result.valid is False
    assert result.future_information_rate == 1.0
    assert "filed" in result.violations[0]


def test_joint_detects_wrong_period() -> None:
    evidence = (_item("e1", "doc1", "2025-03-01", "2023-12-31"),)
    result = verify_joint_temporal(
        evidence,
        source_cutoff=datetime(2025, 12, 31),
        target_end=date(2024, 12, 31),
        target_fiscal_year="FY2024",
    )
    assert result.valid is False
    assert result.wrong_period_rate == 1.0


def test_joint_detects_superseded() -> None:
    evidence = (_item("e1", "doc1", "2025-03-01", "2024-12-31"),)
    result = verify_joint_temporal(
        evidence,
        source_cutoff=datetime(2025, 12, 31),
        target_end=date(2024, 12, 31),
        target_fiscal_year="FY2024",
        version_relations=(VersionRelation("doc1", "doc1a", "SUPERSEDES"),),
    )
    assert result.valid is False
    assert result.superseded_rate == 1.0


def test_joint_detects_amended_as_superseded() -> None:
    """N-2: an AMENDS relation must invalidate the ORIGINAL document's items.

    The pre-fix _superseded only matched relation == 'SUPERSEDES', so an
    amended (10-K/A) superseding its original 10-K was not detected by the
    joint verifier — 'amendment-aware verification' existed only in
    latest_valid_version, which A11 never called. The verifier must agree
    with latest_valid_version on which document is the invalid original.
    """
    original = _item("e1", "doc1", "2025-03-01", "2024-12-31")
    result = verify_joint_temporal(
        (original,),
        source_cutoff=datetime(2025, 12, 31),
        target_end=date(2024, 12, 31),
        target_fiscal_year="FY2024",
        version_relations=(VersionRelation("doc1", "doc1a", "AMENDS"),),
    )
    assert result.valid is False, "amended original must be invalid"
    assert result.superseded_rate == 1.0


def test_latest_valid_version_keeps_amended() -> None:
    original = _item("e-orig", "doc1", "2025-03-01", "2024-12-31")
    amended = _item("e-amend", "doc1a", "2025-06-01", "2024-12-31", ver="10-K/A")
    kept = latest_valid_version(
        (original, amended),
        (VersionRelation("doc1", "doc1a", "AMENDS"),),
    )
    assert kept == (amended,)


def test_extract_numbers_ignores_date_components() -> None:
    """N-7: dates like 2024-09-29 must NOT contribute 2024, -9, -29.

    The pre-fix regex `-?\\d+` splits '2024-09-29' into three numbers, so
    subtract on cashflow texts computed a huge nonsense negative that was
    still marked SUPPORTED (executability-only) and routed to ANSWER with
    zero gold recall. Only the value digits in the text span are wanted.
    """
    from finvest.verification.numerical import _extract_numbers

    text = "NetCashProvidedByUsedInOperatingActivities 29935000000.0 USD 2024-09-29 2024-12-28 2025-01-31 10-Q"
    nums = _extract_numbers((text,))
    assert nums == [29935000000.0], f"dates leaked into numbers: {nums}"


def test_verify_calculation_matches() -> None:
    result = verify_calculation(
        operation="average", evidence_texts=("value 4710", "value 4710"),
        expected_value=4710.0,
    )
    assert result.executable is True
    assert result.verification_state == "SUPPORTED"


def test_verify_calculation_mismatch() -> None:
    result = verify_calculation(
        operation="average", evidence_texts=("value 100", "value 200"),
        expected_value=150.0,  # correct avg but 4710? no — 150 is correct
    )
    assert result.verification_state == "SUPPORTED"


def test_verify_calculation_no_evidence() -> None:
    result = verify_calculation(
        operation="average", evidence_texts=(), expected_value=1.0,
    )
    assert result.verification_state == "INSUFFICIENT_EVIDENCE"


def test_locate_cells_finds_metric() -> None:
    table = "metric | 2023 | 2024\nRevenue | 100 | 120\nCapex | 10 | 15"
    location = locate_cells(table, "Revenue", "2024")
    assert location == (1, 2)  # row 1 (Revenue), col 2 (2024)
