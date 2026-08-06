from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.local_real_data

from finvest.document_intelligence.html_parser import parse_10k_html

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "research/cache/sec/full_10k/aapl-20250927.htm"


@pytest.mark.skipif(not SAMPLE.exists(), reason="full 10-K cache required")
def test_parse_full_10k_produces_units() -> None:
    parsed = parse_10k_html(
        SAMPLE, document_id="aapl-20250927", document_version="10-K",
        filing_date=date(2025, 11, 3),
    )
    assert len(parsed.evidence_units) > 100  # a full 10-K has many units
    assert parsed.document_id == "aapl-20250927"
    # Every unit has a stable ID + section + content.
    ids = {u.evidence_id for u in parsed.evidence_units}
    assert len(ids) == len(parsed.evidence_units)  # unique
    for unit in parsed.evidence_units[:50]:
        assert unit.section
        assert unit.content_hash


@pytest.mark.skipif(not SAMPLE.exists(), reason="full 10-K cache required")
def test_parse_keeps_tables_and_sections() -> None:
    parsed = parse_10k_html(
        SAMPLE, document_id="aapl-20250927", document_version="10-K",
        filing_date=date(2025, 11, 3),
    )
    # A 10-K must have Item 1 (business) and Item 8 (financial statements).
    all_text = " ".join(u.text_span or "" for u in parsed.evidence_units).lower()
    assert "item 1" in all_text or "item 1." in all_text
    # Table-like units (pipe-separated) should exist.
    tables = [u for u in parsed.evidence_units if " | " in (u.text_span or "")]
    assert tables  # financial statements are tables
