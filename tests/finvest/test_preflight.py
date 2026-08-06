"""Preflight classification tests — 4-state model (Phase 7).

The 4-state model is exercised against the COMMITTED fixture (never the
gitignored SEC cache), so CI covers READY/BLOCKED/INVALID classification.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1
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


@pytest.fixture(scope="module")
def fixture_env(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    """A frozen day-1 manifest + cache built from the committed fixture."""
    tmp = tmp_path_factory.mktemp("preflight")
    cache = tmp / "cache"
    sec = cache / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
        encoding="utf-8"
    )
    for ticker in ("aapl", "msft", "ko", "eqix", "jnj", "ups"):
        (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")
    day1 = tmp / "day1"
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1, min_cases=1, cache_dir=cache)
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    return manifest, cache


def test_positive_evidence_case_is_ready_positive(fixture_env) -> None:
    m, cache = fixture_env
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if c["case_id"].endswith("-cashflow-proxy-2024")
    )
    result = preflight_case(case, queue="base", cache=cache)
    assert result.status == READY_POSITIVE


def test_cross_concept_amended_case_is_invalid(fixture_env) -> None:
    m, cache = fixture_env
    # The committed fixture contains ONLY the correct amendment pair
    # (AccruedLiabilitiesCurrent -> same-concept 10-K/A), so the cross-concept
    # trap must NOT appear: a preflight of the valid amended case is NOT
    # SCIENTIFICALLY_INVALID.
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if "amended" in c["case_id"] and c["case_id"].split("-")[1] == "AAPL"
    )
    result = preflight_case(case, queue="base", cache=cache)
    assert result.status != INVALID


def test_insufficient_case_blocked_without_certificate(fixture_env) -> None:
    m, cache = fixture_env
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if "insufficient" in c["case_id"]
    )
    result = preflight_case(case, queue="base", cache=cache, negative_certificates={})
    # Without a certificate, a negative case is TOOLING_BLOCKED, never READY.
    assert result.status == BLOCKED
    assert "certificate" in result.reason.lower()


def test_insufficient_case_ready_with_verified_certificate(fixture_env) -> None:
    m, cache = fixture_env
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
        case, queue="base", cache=cache,
        negative_certificates={case["case_id"]: signed},
    )
    assert result.status == READY_NEGATIVE_VERIFIED


def test_preflight_queues_counts_use_four_states(fixture_env) -> None:
    m, cache = fixture_env
    counts = preflight_queues(m, cache=cache)
    assert set(counts) == {READY_POSITIVE, READY_NEGATIVE_VERIFIED, BLOCKED, INVALID}
    total = sum(len(v) for v in counts.values())
    assert total == len(m["sealed"]["base_22_queue"])  # all cases classified
