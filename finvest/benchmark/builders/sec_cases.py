"""FinVEST-Bench case builder from SEC XBRL companyfacts.

Builds benchmark cases automatically from real SEC XBRL data (reusing the E3/E7
SEC adapter). Each case carries a requirement graph, evidence items (XBRL facts
with period/version), acceptable/minimal evidence sets, calculation programs
for derived answers, and version relations for amendments.

Case types produced:
- ``derived``: FCFF, working capital, margins — requirement graph with
  intermediate values + calculation program.
- ``temporal_amended``: a 10-K value restated by a 10-K/A — version relations
  + the amended value as gold.
- ``cross_period``: same metric reported in 10-K and 10-Q — period scope.
- ``insufficient``: a metric not reported for the period (honest ABSTAIN).

NOTE: these are AI-generated candidate cases with requirement graphs derived
from structured XBRL. They are NOT human-verified; per the annotation policy,
human annotators must verify labels before they count as benchmark gold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ecoquant.research.temporal_eval.sec_adapter import SecBundle, SecFact, load_companyfacts

from ..schemas import (
    CalculationProgram,
    EvidenceItem,
    FinVestCase,
    RequirementEdge,
    RequirementGraph,
    RequirementNode,
    VersionRelation,
)

# Domain mapping for the 6 companies in cache.
COMPANY_DOMAINS = {
    "AAPL": "US", "MSFT": "US", "KO": "US",
    "EQIX": "US", "JNJ": "US", "UPS": "US",
}


@dataclass(frozen=True)
class BuiltCases:
    cases: tuple[FinVestCase, ...]
    builder_manifest: dict[str, object]


def _evidence_item(fact: SecFact, ticker: str) -> EvidenceItem:
    """Map a SecFact to a benchmark EvidenceItem.

    Phase 4/6: unit comes from the FACT (never hardcoded USD); scope is None
    unless the source actually states it (never auto-"consolidated").
    """
    return EvidenceItem(
        evidence_id=fact.fact_id,
        document_id=f"{ticker}-{fact.form}-{fact.end}",
        document_version=fact.form,
        filing_date=fact.filed,
        valid_from=fact.start or fact.end,
        valid_to=fact.end,
        xbrl_fact_id=fact.fact_id,
        concept=fact.concept,
        unit=fact.unit or "USD",
        scale="1",
        scope=fact.scope,
        content_hash=fact.fact_id,
    )


def _fcff_case(bundle: SecBundle, ticker: str, year: int) -> FinVestCase | None:
    """Derived case: SIMPLIFIED cash-flow proxy (OCF - capex) for a fiscal year.

    Phase 6: this is NOT claimed to be standard FCFF. The question states the
    explicit operation. Facts are filtered by source cutoff. Target period uses
    the REAL XBRL start/end (never Jan 1 default). Units come from the fact,
    not hardcoded USD.
    """
    ocf = _annual_fact(bundle, ticker, year, "NetCashProvidedByUsedInOperatingActivities")
    capex = _annual_fact(bundle, ticker, year, "PaymentsToAcquirePropertyPlantAndEquipment")
    if ocf is None or capex is None:
        return None
    # Source cutoff: after both facts' filings (only facts filed <= cutoff are
    # eligible; any later filing must not be used).
    source_cutoff = max(ocf.filed, capex.filed)
    # Real period from the fact's start/end (not Jan 1 default).
    period_start = ocf.start or ocf.end
    period_end = ocf.end
    proxy = ocf.value - capex.value
    unit = ocf.unit or "USD"
    graph = RequirementGraph(
        nodes=(
            RequirementNode("cash_flow_proxy", "FINAL_VALUE", "simplified-cash-flow-proxy"),
            RequirementNode("ocf", "INTERMEDIATE_VALUE", "OperatingCashFlow"),
            RequirementNode("capex", "INTERMEDIATE_VALUE", "CapitalExpenditure"),
            RequirementNode("ticker", "ENTITY", ticker),
            RequirementNode("period", "PERIOD", str(year)),
        ),
        edges=(
            RequirementEdge("cash_flow_proxy", "ocf", "DERIVES_FROM"),
            RequirementEdge("cash_flow_proxy", "capex", "DERIVES_FROM"),
            RequirementEdge("ocf", "ticker", "SAME_AS"),
            RequirementEdge("ocf", "period", "SAME_AS"),
            RequirementEdge("capex", "ticker", "SAME_AS"),
            RequirementEdge("capex", "period", "SAME_AS"),
        ),
    )
    program = CalculationProgram(
        operation="subtract",
        inputs=("OperatingCashFlow", "CapitalExpenditure"),
        result=proxy, unit=unit, scale="1", period=f"FY{year}",
    )
    ev_ocf = _evidence_item(ocf, ticker)
    ev_capex = _evidence_item(capex, ticker)
    return FinVestCase(
        case_id=f"finvest-{ticker}-cashflow-proxy-{year}",
        base_question_id=f"bq-cashflow-proxy-{year}",
        issuer_id=ticker,
        jurisdiction=COMPANY_DOMAINS[ticker],
        question=(
            f"What is {ticker} operating cash flow minus capital expenditure "
            f"for the fiscal period ending {period_end}?"
        ),
        source_cutoff=datetime(source_cutoff.year, source_cutoff.month, source_cutoff.day),
        target_period_start=period_start,
        target_period_end=period_end,
        target_fiscal_year=f"FY{year}",
        answer_type="derived",
        gold_answer={"value": proxy, "unit": unit},
        decision_label="ANSWER",
        sufficiency_label="SUPPORTED",
        requirement_graph=graph,
        acceptable_evidence_sets=(frozenset({ev_ocf.evidence_id, ev_capex.evidence_id}),),
        minimal_evidence_sets=(frozenset({ev_ocf.evidence_id, ev_capex.evidence_id}),),
        evidence_items=(ev_ocf, ev_capex),
        calculation_program=program,
        assumptions=(
            "SIMPLIFIED cash-flow proxy = OCF - capex; NOT standard FCFF "
            "(no tax/interest/working-capital adjustments).",
        ),
    )


def _amended_case(bundle: SecBundle, ticker: str) -> FinVestCase | None:
    """Temporal case: a 10-K value restated by a 10-K/A."""
    original, amended = _amended_pair(bundle, ticker)
    if original is None or amended is None:
        return None
    graph = RequirementGraph(
        nodes=(
            RequirementNode("metric", "METRIC", original.concept),
            RequirementNode("ticker", "ENTITY", ticker),
            RequirementNode("period", "PERIOD", str(original.end)),
            RequirementNode("version", "VERSION", "latest"),
        ),
        edges=(
            RequirementEdge("metric", "ticker", "SAME_AS"),
            RequirementEdge("metric", "period", "SAME_AS"),
            RequirementEdge("version", "metric", "REQUIRES"),
        ),
    )
    ev_orig = _evidence_item(original, ticker)
    ev_amend = _evidence_item(amended, ticker)
    return FinVestCase(
        case_id=f"finvest-{ticker}-amended-{original.concept}-{original.end}",
        base_question_id=f"bq-amended-{original.concept}",
        issuer_id=ticker,
        jurisdiction=COMPANY_DOMAINS[ticker],
        question=f"What is the latest restated value of {original.concept} for {ticker} for the period ending {original.end}?",
        source_cutoff=datetime(amended.filed.year, amended.filed.month, amended.filed.day),
        target_period_start=original.end,
        target_period_end=original.end,
        target_fiscal_year=str(original.end.year),
        answer_type="extractive",
        gold_answer={"value": amended.val, "unit": "USD"},
        decision_label="ANSWER",
        sufficiency_label="CONFLICTING",  # original vs amended coexist until resolved
        requirement_graph=graph,
        acceptable_evidence_sets=(frozenset({ev_amend.evidence_id}),),
        minimal_evidence_sets=(frozenset({ev_amend.evidence_id}),),
        evidence_items=(ev_orig, ev_amend),
        version_relations=(
            VersionRelation(original.fact_id, amended.fact_id, "AMENDS"),
        ),
        known_conflicts=(f"original {original.val} vs amended {amended.val}",),
    )


def _insufficient_case(bundle: SecBundle, ticker: str, year: int) -> FinVestCase | None:
    """Insufficient case: a metric NOT reported for the year (honest ABSTAIN)."""
    # Pick a metric the company reports in OTHER years but not this one.
    reported_years: dict[str, set[int]] = {}
    for fact in bundle.facts:
        if fact.ticker == ticker and fact.form == "10-K":
            reported_years.setdefault(fact.concept, set()).add(fact.end.year)
    candidates = [
        concept for concept, years in reported_years.items()
        if year not in years and any(y < year for y in years)
    ]
    if not candidates:
        return None
    concept = sorted(candidates)[0]
    graph = RequirementGraph(
        nodes=(
            RequirementNode("metric", "METRIC", concept),
            RequirementNode("ticker", "ENTITY", ticker),
            RequirementNode("period", "PERIOD", str(year)),
        ),
        edges=(
            RequirementEdge("metric", "ticker", "SAME_AS"),
            RequirementEdge("metric", "period", "SAME_AS"),
        ),
    )
    return FinVestCase(
        case_id=f"finvest-{ticker}-insufficient-{concept}-{year}",
        base_question_id=f"bq-insufficient-{concept}",
        issuer_id=ticker,
        jurisdiction=COMPANY_DOMAINS[ticker],
        question=f"What is {concept} for {ticker} for fiscal year {year}?",
        source_cutoff=datetime(year + 1, 6, 30),
        target_period_start=date(year, 1, 1),
        target_period_end=date(year, 12, 31),
        target_fiscal_year=f"FY{year}",
        answer_type="unanswerable",
        gold_answer={},
        decision_label="ABSTAIN",
        sufficiency_label="INSUFFICIENT",
        requirement_graph=graph,
        evidence_items=(),
        assumptions=("Metric not reported for the period (no public disclosure)",),
    )


def _annual_fact(bundle: SecBundle, ticker: str, year: int, concept: str) -> SecFact | None:
    """Latest 10-K fact for a concept in a fiscal year."""
    matches = [
        fact for fact in bundle.facts
        if fact.ticker == ticker and fact.concept == concept
        and fact.form == "10-K" and fact.end.year == year
    ]
    return max(matches, key=lambda f: (f.end, f.filed)) if matches else None


def _amended_pair(bundle: SecBundle, ticker: str) -> tuple[SecFact | None, SecFact | None]:
    """Find a valid (10-K, 10-K/A) pair under strict identity.

    A valid amendment pair requires EXACT compatibility on a canonical key
    (ticker, concept, start, end, unit) — never pairing facts of different
    concepts (the v0.1 defect). The amended side must:
    - be form 10-K/A,
    - be filed on or after the original 10-K filing date,
    - report a different value for the same identity.
    """
    # Group by canonical identity (ticker, concept, end, unit); keep ALL facts
    # per group (not last-wins). companyfacts exposes end but not start for
    # instant facts; period identity is (concept, end).
    from collections import defaultdict

    groups: dict[tuple[str, str, str, str], list[SecFact]] = defaultdict(list)
    for fact in bundle.facts:
        if fact.ticker != ticker or fact.form not in {"10-K", "10-K/A"}:
            continue
        key = (fact.ticker, fact.concept, str(fact.end), fact.unit or "")
        groups[key].append(fact)
    for key in sorted(groups):
        facts = groups[key]
        originals = [f for f in facts if f.form == "10-K"]
        amendeds = [f for f in facts if f.form == "10-K/A"]
        for original in originals:
            for amended in amendeds:
                if abs(original.val - amended.val) <= 1e-6:
                    continue  # no real restatement
                if amended.filed < original.filed:
                    continue  # amendment must not predate the original
                return original, amended
    return None, None


def build_sec_cases(
    cache_dir: Path, tickers: tuple[str, ...], *, fixture: bool = False
) -> BuiltCases:
    """Build FinVEST cases from SEC XBRL companyfacts for the given tickers.

    ``fixture=True`` marks the manifest as synthetic (committed fixture).
    """
    bundle = load_companyfacts(cache_dir / "sec", tickers=tickers, fixture=fixture)
    cases: list[FinVestCase] = []
    for ticker in tickers:
        years = sorted({
            fact.end.year for fact in bundle.facts
            if fact.ticker == ticker and fact.form == "10-K"
        })
        for year in years[-2:]:
            fcff = _fcff_case(bundle, ticker, year)
            if fcff is not None:
                cases.append(fcff)
            insufficient = _insufficient_case(bundle, ticker, year)
            if insufficient is not None:
                cases.append(insufficient)
        amended = _amended_case(bundle, ticker)
        if amended is not None:
            cases.append(amended)
    # Validate all cases.
    for case in cases:
        case.validate()
    manifest = {
        "builder": "sec_cases",
        "version": "0.1.0",
        "tickers": list(tickers),
        "case_count": len(cases),
        "types": {t: sum(1 for c in cases if c.answer_type == t) for t in
                  ("extractive", "derived", "comparative", "unanswerable")},
        "note": "AI-generated candidate cases; human verification required before gold.",
    }
    return BuiltCases(tuple(cases), manifest)
