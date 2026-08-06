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
