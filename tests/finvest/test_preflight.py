"""Preflight classification tests — 4-state model (Phase 7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finvest.human_study.web.services.negative_evidence import new_certificate, sign_certificate
from finvest.human_study.web.services.preflight import (
    READY_NEGATIVE_VERIFIED,
    READY_POSITIVE,
    BLOCKED,
    INVALID,
    preflight_case,
    preflight_queues,
)

ROOT = Path(__file__).resolve().parents[2]
REAL_MANIFEST = ROOT / "human_review/day1/v0.1/QUEUE_MANIFEST.json"
CACHE = ROOT / "research/cache"

pytestmark = pytest.mark.local_real_data


def test_positive_evidence_case_is_ready_positive() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    case = next(c for c in m["sealed"]["base_22_queue"] if "fcff-2024" in c["case_id"])
    result = preflight_case(case, queue="base", cache=CACHE)
    assert result.status == READY_POSITIVE


def test_cross_concept_amended_case_is_invalid() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if c["case_id"] == "finvest-AAPL-amended-SalesRevenueNet-2009-03-28"
    )
    result = preflight_case(case, queue="base", cache=CACHE)
    assert result.status == INVALID
    assert "cross-concept" in result.reason


def test_insufficient_case_blocked_without_certificate() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if "insufficient" in c["case_id"]
    )
    result = preflight_case(case, queue="base", cache=CACHE, negative_certificates={})
    # Without a certificate, a negative case is TOOLING_BLOCKED, never READY.
    assert result.status == BLOCKED
    assert "certificate" in result.reason.lower()


def test_insufficient_case_ready_with_verified_certificate() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if "insufficient" in c["case_id"]
    )
    cert = new_certificate(
        case_id=case["case_id"],
        query_terms=("AccruedLiabilitiesCurrent",),
        document_collection=("10-K", "10-K/A"),
        source_cutoff=case["source_cutoff"],
        human_reviewer="ELIAN_PRIMARY",
    )
    signed = sign_certificate(cert, reviewer_id="ELIAN_PRIMARY")
    result = preflight_case(
        case, queue="base", cache=CACHE,
        negative_certificates={case["case_id"]: signed},
    )
    assert result.status == READY_NEGATIVE_VERIFIED


def test_preflight_queues_counts_use_four_states() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    counts = preflight_queues(m, cache=CACHE)
    assert set(counts) == {READY_POSITIVE, READY_NEGATIVE_VERIFIED, BLOCKED, INVALID}
    total = sum(len(v) for v in counts.values())
    assert total == 22  # all v0.1 cases classified
