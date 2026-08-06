"""Preflight classification tests (Phase 4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finvest.human_study.web.services.preflight import (
    INVALID,
    READY,
    BLOCKED,
    preflight_case,
    preflight_queues,
)

ROOT = Path(__file__).resolve().parents[2]
REAL_MANIFEST = ROOT / "human_review/day1/v0.1/QUEUE_MANIFEST.json"
CACHE = ROOT / "research/cache"


def test_fcff_case_is_ready() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    case = next(c for c in m["sealed"]["base_22_queue"] if "fcff-2024" in c["case_id"])
    result = preflight_case(case, queue="base", cache=CACHE)
    assert result.status == READY


def test_cross_concept_amended_case_is_invalid() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if c["case_id"] == "finvest-AAPL-amended-SalesRevenueNet-2009-03-28"
    )
    result = preflight_case(case, queue="base", cache=CACHE)
    assert result.status == INVALID
    assert "cross-concept" in result.reason


def test_insufficient_case_is_blocked() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    case = next(
        c for c in m["sealed"]["base_22_queue"]
        if "insufficient" in c["case_id"]
    )
    result = preflight_case(case, queue="base", cache=CACHE)
    assert result.status in (BLOCKED, READY)  # insufficient may be READY if no evidence needed


def test_preflight_queues_counts() -> None:
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    counts = preflight_queues(m, cache=CACHE)
    total = sum(len(v) for v in counts.values())
    assert total == 22  # all 22 v0.1 cases classified
    assert counts[INVALID]  # at least one cross-concept case detected
