"""E7: per-company commercial analysis with evidence-linked outputs.

Combines the concept resolver + ratio calculators into a ``CompanyAnalysis``
that separates facts (direct XBRL values), inferences (derived from facts,
clearly labeled), and assumptions (documented choices), and reports an
evidence-sufficiency classification. No metric is reported without a source;
missing evidence yields None, not a fabricated value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ecoquant.research.temporal_eval.sec_adapter import SecBundle

from .concepts import resolve_concept
from .metrics import (
    debt_to_equity,
    fcff,
    gross_margin,
    operating_margin,
    reinvestment_rate,
    roic,
    working_capital,
)


@dataclass(frozen=True)
class EvidenceItem:
    """One traceable source fact used in the analysis."""

    metric: str
    concept: str
    value: float
    period_end: str
    fact_id: str


@dataclass(frozen=True)
class Inference:
    """A derived value labeled as inference (not a direct fact)."""

    metric: str
    value: float
    reason: str
    source_metrics: tuple[str, ...]


@dataclass(frozen=True)
class CompanyAnalysis:
    ticker: str
    year: int
    metrics: dict[str, float | None]
    evidence_sources: dict[str, dict[str, str] | None]
    inferences: list[Inference]
    assumptions: list[str]
    evidence_sufficiency: str  # SUFFICIENT | PARTIAL | INSUFFICIENT


# Headline metrics required for SUFFICIENT evidence.
CORE_METRICS = ("revenue", "net_income")
HEADLINE_METRICS = ("revenue", "gross_margin", "operating_margin", "fcff", "roic")


def analyze_company(bundle: SecBundle, ticker: str, year: int) -> CompanyAnalysis:
    """Produce an evidence-linked commercial analysis for one company/year."""
    # Resolve direct facts.
    resolved: dict[str, object] = {}
    evidence_sources: dict[str, dict[str, str] | None] = {}
    for metric in (
        "revenue", "gross_profit", "operating_income", "net_income",
        "cash", "current_assets", "current_liabilities", "inventory",
        "long_term_debt", "total_debt", "capex", "equity",
        "operating_cash_flow", "interest_expense",
    ):
        rv = resolve_concept(bundle, ticker, metric, year)
        resolved[metric] = rv
        evidence_sources[metric] = (
            {
                "concept": rv.concept,
                "value": rv.value,
                "period_end": rv.period_end.isoformat(),
                "fact_id": rv.fact_id,
                "form": rv.form,
            }
            if rv is not None
            else None
        )

    def value(metric: str) -> float | None:
        rv = resolved.get(metric)
        return rv.value if rv is not None else None

    # Compute ratios; None when evidence missing.
    metrics: dict[str, float | None] = {
        "revenue": value("revenue"),
        "gross_margin": gross_margin(value("gross_profit"), value("revenue")),
        "operating_margin": operating_margin(value("operating_income"), value("revenue")),
        "net_income": value("net_income"),
        "fcff": fcff(value("operating_cash_flow"), value("capex")),
        "roic": roic(
            value("net_income"),
            equity=value("equity"),
            total_debt=value("total_debt"),
            cash=value("cash"),
        ),
        "reinvestment_rate": reinvestment_rate(value("capex"), value("operating_cash_flow")),
        "debt_to_equity": debt_to_equity(value("total_debt"), value("equity")),
    }

    # Working capital: direct if CurrentAssets/Liabilities resolve; else a
    # documented inference using cash + inventory as a proxy (clearly labeled).
    inferences: list[Inference] = []
    working_capital_value = None
    ca, cl = value("current_assets"), value("current_liabilities")
    if ca is not None and cl is not None:
        working_capital_value = working_capital(ca, cl)
    elif ca is None and cl is None and value("cash") is not None and value("inventory") is not None:
        proxy_assets = value("cash") + value("inventory")
        if cl is not None:
            working_capital_value = working_capital(proxy_assets, cl)
            inferences.append(Inference(
                metric="working_capital",
                value=working_capital_value,
                reason="CurrentAssets not reported; proxied as cash + inventory (documented inference)",
                source_metrics=("cash", "inventory", "current_liabilities"),
            ))
    metrics["working_capital"] = working_capital_value

    # Evidence sufficiency.
    core_present = sum(1 for m in CORE_METRICS if metrics.get(m) is not None)
    headline_present = sum(1 for m in HEADLINE_METRICS if metrics.get(m) is not None)
    if core_present == len(CORE_METRICS) and headline_present >= 4:
        sufficiency = "SUFFICIENT"
    elif core_present >= 1:
        sufficiency = "PARTIAL"
    else:
        sufficiency = "INSUFFICIENT"

    assumptions = [
        "ROIC ≈ net income / (equity + debt − cash); no tax/interest adjustment",
        "FCFF ≈ operating cash flow − capex; no working-capital delta adjustment",
        "Annual values from the 10-K for the fiscal year; amended values supersede originals",
    ]

    return CompanyAnalysis(
        ticker=ticker,
        year=year,
        metrics=metrics,
        evidence_sources=evidence_sources,
        inferences=inferences,
        assumptions=assumptions,
        evidence_sufficiency=sufficiency,
    )
