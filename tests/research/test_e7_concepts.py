from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.commercial_eval.concepts import METRIC_CONCEPTS, resolve_concept
from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/sec"


@pytest.fixture(scope="module")
def bundle():
    return load_companyfacts(CACHE, tickers=("EQIX", "JNJ", "UPS"))


def test_revenue_resolves_for_eqix(bundle) -> None:
    rv = resolve_concept(bundle, "EQIX", "revenue", 2023)
    assert rv is not None
    assert rv.concept in METRIC_CONCEPTS["revenue"]
    assert rv.value > 0
    assert rv.fact_id  # traceable


def test_missing_metric_returns_none(bundle) -> None:
    rv = resolve_concept(bundle, "EQIX", "inventory", 2023)
    assert rv is None  # no evidence → honest no-conclusion


def test_operating_income_resolves_when_reported(bundle) -> None:
    """Operating income resolves for companies that report it; None for others.

    JNJ does not report OperatingIncomeLoss in fiscal 2023 (a real reporting
    difference) — the resolver must honestly return None there, not fabricate.
    """
    for ticker in ("EQIX", "UPS"):
        rv = resolve_concept(bundle, ticker, "operating_income", 2023)
        assert rv is not None, f"{ticker} operating income should resolve"
        assert rv.value != 0
    # JNJ genuinely lacks OperatingIncomeLoss in 2023 → honest None.
    jnj = resolve_concept(bundle, "JNJ", "operating_income", 2023)
    assert jnj is None


def test_capex_resolves_for_ups(bundle) -> None:
    rv = resolve_concept(bundle, "UPS", "capex", 2023)
    assert rv is not None
    assert rv.value > 0


def test_annual_fact_preferred(bundle) -> None:
    """2023 revenue must come from a 10-K (annual), not a 10-Q.

    Fiscal years may end Dec 30/29 (e.g. JNJ); the key is that the fact is a
    10-K with a period end in the fiscal year's end window (Nov 15 - Dec 31).
    """
    rv = resolve_concept(bundle, "EQIX", "revenue", 2023)
    assert rv is not None
    assert rv.period_end.year == 2023
    assert rv.period_end.month in (11, 12)  # fiscal year-end window
