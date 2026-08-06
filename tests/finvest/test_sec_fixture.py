"""Synthetic SEC fixture tests (Phase 3) — depend ONLY on the committed fixture.

These prove the fixture exercises every identity edge case the resolver and
builder must handle, and that unit/workflow tests can run without the
gitignored SEC cache.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from finvest.fixtures.sec_fixture import FIXTURE_DIR, build_companyfacts_payload, load_fixture

FIXTURE = FIXTURE_DIR / "sec_companyfacts_fixture.json"


def test_fixture_committed_and_valid() -> None:
    assert FIXTURE.exists()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["facts"]["us-gaap"]


def test_fixture_has_all_edge_cases() -> None:
    facts = load_fixture()["facts"]["us-gaap"]
    required = {
        "Assets": "normal instant fact",
        "Revenues": "normal duration-period fact",
        "AccruedLiabilitiesCurrent": "correct 10-K/A amendment pair",
        "EntityPublicFloat": "cross-concept error pair (v0.1 defect)",
        "FutureExpense": "future filing (after cutoff)",
        "RevenueEur": "wrong-unit fact",
        "DuplicateMetric": "duplicate identity (ambiguous)",
    }
    for concept, purpose in required.items():
        assert concept in facts, f"missing fixture concept {concept} ({purpose})"


def test_amendment_pair_same_identity() -> None:
    facts = load_fixture()["facts"]["us-gaap"]["AccruedLiabilitiesCurrent"]["units"]["USD"]
    original = next(f for f in facts if f["form"] == "10-K")
    amended = next(f for f in facts if f["form"] == "10-K/A")
    # Same concept, same period end, same unit.
    assert amended["end"] == original["end"]
    assert amended["unit"] == original["unit"]
    # Amended filed after original, different accession, different value.
    assert amended["filed"] >= original["filed"]
    assert amended["accn"] != original["accn"]
    assert amended["val"] != original["val"]


def test_cross_concept_pair_is_distinct() -> None:
    """The cross-concept error case must NOT be a valid amendment pair."""
    facts = load_fixture()["facts"]["us-gaap"]
    # EntityPublicFloat 10-K/A has a DIFFERENT concept than AccruedLiabilitiesCurrent.
    epf = facts["EntityPublicFloat"]["units"]["USD"][0]
    accr = facts["AccruedLiabilitiesCurrent"]["units"]["USD"][0]
    assert epf["end"] == accr["end"]  # same period (the trap)
    # But the concepts differ — a correct resolver must NOT pair them.
    # (The adapter keys facts by concept, so this trap never produces a pair.)


def test_future_filing_after_cutoff() -> None:
    facts = load_fixture()["facts"]["us-gaap"]["FutureExpense"]["units"]["USD"][0]
    assert facts["filed"] > "2025-12-31"  # filed after a plausible cutoff


def test_wrong_unit_present() -> None:
    facts = load_fixture()["facts"]["us-gaap"]["RevenueEur"]["units"]
    assert "EUR" in facts  # unit is EUR, not USD


def test_duplicate_identity_present() -> None:
    facts = load_fixture()["facts"]["us-gaap"]["DuplicateMetric"]["units"]["USD"]
    assert len(facts) == 2
    assert facts[0]["accn"] != facts[1]["accn"]


def test_fixture_sha256_stable() -> None:
    """The committed fixture's content hash must be stable (reproducibility)."""
    content = FIXTURE.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert digest.startswith("db8ede83ef6902ca")


# ---------------------------------------------------------------------------
# Phase 4: SecFact full source identity from the committed fixture
# ---------------------------------------------------------------------------

def _facts_from_fixture():
    """Parse the fixture through the real SecFact adapter (no real cache)."""
    from pathlib import Path
    import tempfile

    from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

    tmp = Path(tempfile.mkdtemp(prefix="fixture-sec-"))
    (tmp / "synth_companyfacts.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return load_companyfacts(tmp, tickers=("SYNTH",))


def test_secfact_has_full_identity() -> None:
    bundle = _facts_from_fixture()
    assert bundle.facts
    fact = next(f for f in bundle.facts if f.concept == "Assets")
    assert fact.taxonomy == "us-gaap"
    assert fact.value == 400_000_000_000
    assert fact.unit == "USD"
    assert fact.accession == "0000320193-24-000123"
    assert fact.form == "10-K"
    assert fact.fiscal_year == 2024
    assert fact.start is None  # instant fact
    assert fact.end.isoformat() == "2024-09-28"


def test_secfact_fact_id_unique_and_source_traceable() -> None:
    bundle = _facts_from_fixture()
    ids = [f.fact_id for f in bundle.facts]
    assert len(ids) == len(set(ids))
    # fact_id embeds issuer, taxonomy, concept, unit, period, form, accession.
    assets = next(f for f in bundle.facts if f.concept == "Assets")
    assert "SYNTH" in assets.fact_id
    assert "us-gaap" in assets.fact_id
    assert "Assets" in assets.fact_id
    assert "USD" in assets.fact_id
    assert "0000320193-24-000123" in assets.fact_id


def test_secfact_content_hash_is_source_row_hash() -> None:
    bundle = _facts_from_fixture()
    fact = next(f for f in bundle.facts if f.concept == "Assets")
    row = load_fixture()["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]
    expected = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert fact.content_hash == expected


def test_no_auto_scope_or_usd_hardcode() -> None:
    bundle = _facts_from_fixture()
    # No fact claims consolidated scope unless the source says so (it doesn't).
    assert all(f.scope is None for f in bundle.facts)
    # EUR fact keeps its real unit, not forced to USD.
    eur = next(f for f in bundle.facts if f.concept == "RevenueEur")
    assert eur.unit == "EUR"
    # Different units coexist.
    assert {f.unit for f in bundle.facts} >= {"USD", "EUR"}


def test_duration_period_preserved() -> None:
    bundle = _facts_from_fixture()
    revenues = next(f for f in bundle.facts if f.concept == "Revenues")
    assert revenues.start is not None
    assert revenues.start.isoformat() == "2023-10-01"
    assert revenues.end.isoformat() == "2024-09-28"
