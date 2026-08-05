from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.commercial_eval.analyze import analyze_company
from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/sec"


@pytest.fixture(scope="module")
def bundle():
    return load_companyfacts(CACHE, tickers=("EQIX", "JNJ", "UPS"))


def test_eqix_analysis_has_metrics_with_sources(bundle) -> None:
    analysis = analyze_company(bundle, "EQIX", 2023)
    assert analysis.ticker == "EQIX"
    assert analysis.year == 2023
    # Metrics EQIX reports must resolve.
    assert analysis.metrics["revenue"] is not None
    assert analysis.metrics["operating_margin"] is not None
    # EQIX does not report GrossProfit in XBRL → gross_margin honestly None.
    assert analysis.metrics["gross_margin"] is None
    # Every metric value has a source.
    for metric, entry in analysis.evidence_sources.items():
        if entry is not None:
            assert entry["concept"]
            assert entry["fact_id"]
            assert entry["period_end"]


def test_evidence_sufficiency_classification(bundle) -> None:
    eqix = analyze_company(bundle, "EQIX", 2023)
    # EQIX reports core metrics → SUFFICIENT or PARTIAL, never INSUFFICIENT.
    assert eqix.evidence_sufficiency in ("SUFFICIENT", "PARTIAL")


def test_facts_inferences_assumptions_separated(bundle) -> None:
    analysis = analyze_company(bundle, "EQIX", 2023)
    # Inferences are explicitly labeled (working-capital proxy etc.).
    assert "inferences" in analysis.__dict__ or analysis.inferences == []
    assert isinstance(analysis.inferences, list)
    for inference in analysis.inferences:
        assert "metric" in inference
        assert "reason" in inference


def test_no_conclusion_without_evidence(bundle) -> None:
    """A metric with no resolved evidence must be None, never fabricated."""
    analysis = analyze_company(bundle, "EQIX", 1990)  # pre-EDGAR year
    assert analysis.evidence_sufficiency == "INSUFFICIENT"
    assert analysis.metrics["revenue"] is None
