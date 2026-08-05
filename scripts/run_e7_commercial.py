"""One-command E7 cross-domain commercial analysis over SEC XBRL facts.

Usage: python scripts/run_e7_commercial.py
Analyzes 6 companies across 4 domains for their latest 2 fiscal years,
writes research/results/e7_commercial_summary.json. Exits 0 iff all analyses
completed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/results/e7_commercial_summary.json"

# 6 companies across 4 domains.
COMPANIES = {
    "EQIX": "data-centre/digital-infrastructure",
    "JNJ": "healthcare/pharmaceutical",
    "UPS": "industrial/logistics",
    "AAPL": "technology",
    "MSFT": "technology",
    "KO": "consumer-staples",
}


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from ecoquant.research.commercial_eval.analyze import analyze_company
    from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

    bundle = load_companyfacts(ROOT / "research/cache/sec", tickers=tuple(COMPANIES))
    # Latest complete fiscal year per company: fiscal year-ends differ (Apple
    # ends Sep, MSFT ends Jun, JNJ/UPS/KO/EQIX end Dec). For each calendar year,
    # take the 10-K fact with the latest period end (the annual report), then
    # pick the two most recent calendar years that have one.
    latest_years: dict[str, int | None] = {}
    for ticker in COMPANIES:
        annual_ends = {
            fact.end for fact in bundle.facts
            if fact.ticker == ticker and fact.form == "10-K"
        }
        by_calendar_year: dict[int, object] = {}
        for end in annual_ends:
            by_calendar_year[end.year] = max(
                by_calendar_year.get(end.year, end), end
            )
        complete_years = sorted(
            year for year, end in by_calendar_year.items() if end.month >= 6
        )
        latest_years[ticker] = complete_years[-1] if complete_years else None

    analyses: dict[str, object] = {}
    for ticker, domain in COMPANIES.items():
        year = latest_years[ticker]
        if year is None:
            analyses[ticker] = {"error": "no 10-K facts found"}
            continue
        company_analyses = {}
        for y in (year, year - 1):
            analysis = analyze_company(bundle, ticker, y)
            company_analyses[str(y)] = {
                "metrics": analysis.metrics,
                "evidence_sufficiency": analysis.evidence_sufficiency,
                "evidence_sources": analysis.evidence_sources,
                "inferences": [
                    {"metric": i.metric, "value": i.value, "reason": i.reason}
                    for i in analysis.inferences
                ],
                "assumptions": analysis.assumptions,
            }
        analyses[ticker] = {"domain": domain, "years": company_analyses}

    payload = {
        "experiment": "e7-cross-domain-commercial-analysis",
        "note": (
            "Evidence-to-decision applied to commercial underwriting over SEC "
            "XBRL companyfacts. Every metric carries a source (concept, period, "
            "fact_id); facts/inferences/assumptions separated; None when evidence "
            "is insufficient. Public data only; no private cases."
        ),
        "companies": analyses,
        "all_ok": all("error" not in v for v in analyses.values()),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
