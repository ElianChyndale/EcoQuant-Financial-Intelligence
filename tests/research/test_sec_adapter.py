from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ecoquant.research.temporal_eval.sec_adapter import SecBundle, SecFact, load_companyfacts

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/sec"


@pytest.fixture(scope="module")
def bundle() -> SecBundle:
    return load_companyfacts(CACHE, tickers=("AAPL", "MSFT", "KO"))


def test_sec_bundle_counts(bundle) -> None:
    assert len(bundle.facts) > 10000
    assert {"AAPL", "MSFT", "KO"} <= set(bundle.companies)


def test_sec_fact_fields(bundle) -> None:
    fact = bundle.facts[0]
    assert isinstance(fact, SecFact)
    assert fact.fact_id and fact.ticker and fact.concept
    assert isinstance(fact.end, date)
    assert isinstance(fact.filed, date)
    assert isinstance(fact.val, float)


def test_restatements_detected(bundle) -> None:
    """AAPL Assets 2008-09-27 has 10-K and 10-K/A with different values."""
    restated = [
        fact for fact in bundle.facts
        if fact.ticker == "AAPL" and fact.concept == "Assets" and str(fact.end) == "2008-09-27"
    ]
    assert len({fact.val for fact in restated}) >= 2


def test_fact_ids_unique(bundle) -> None:
    ids = [fact.fact_id for fact in bundle.facts]
    assert len(ids) == len(set(ids))


def test_forms_are_temporal_relevant(bundle) -> None:
    """Facts must be 10-K / 10-Q / 10-K/A (temporal filings)."""
    allowed = {"10-K", "10-Q", "10-K/A"}
    assert all(fact.form in allowed for fact in bundle.facts)
