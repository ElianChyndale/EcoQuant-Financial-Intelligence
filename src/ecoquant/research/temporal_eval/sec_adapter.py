"""SEC EDGAR XBRL CompanyFacts adapter for the E3 temporal evaluation.

Parses SEC companyfacts JSON (public domain, no API key; descriptive User-Agent
required) into a flat ``SecFact`` list with explicit valid time (``end``) and
source time (``filed``). Only temporal filings (10-K / 10-Q / 10-K/A) are kept;
restatements surface as the same (concept, end, form) with differing ``val``
across ``filed`` dates.

Raw JSON is cache-only in ``research/cache/sec/`` (gitignored); only hashes and
derived metadata are committed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

TEMPORAL_FORMS = frozenset({"10-K", "10-Q", "10-K/A"})


@dataclass(frozen=True)
class SecFact:
    """One XBRL fact with FULL source identity (Phase 4).

    ``fact_id`` uniquely points to one raw source row. It is NOT derived from
    concept/end/filed/form alone (that would collide); it includes issuer,
    taxonomy, concept, unit, period, form, and accession.
    """

    fact_id: str
    ticker: str
    taxonomy: str
    concept: str
    value: float
    unit: str
    start: date | None
    end: date
    filed: date
    accession: str
    form: str
    fiscal_year: int | None
    fiscal_period: str | None
    frame: str | None
    dimensions: str | None
    scope: str | None  # None unless actually known from source (no auto "consolidated")
    content_hash: str  # sha256 over the exact raw source row

    # Backward-compatible alias for existing callers.
    @property
    def val(self) -> float:
        return self.value


@dataclass(frozen=True)
class SecBundle:
    facts: tuple[SecFact, ...]
    companies: tuple[str, ...]
    manifest: dict[str, object]


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def load_companyfacts(cache_dir: Path, tickers: tuple[str, ...] = ("AAPL", "MSFT", "KO")) -> SecBundle:
    """Load SEC companyfacts for the given tickers into a SecBundle."""
    facts: list[SecFact] = []
    manifest: dict[str, object] = {
        "dataset_id": "sec-edgar-companyfacts-v1",
        "adapter_version": "0.1.0",
        "tickers": list(tickers),
        "source": "https://data.sec.gov/api/xbrl/companyfacts/",
        "license": "public-domain",
        "redistribution_status": "cache_only",
    }
    for ticker in tickers:
        path = cache_dir / f"{ticker.lower()}_companyfacts.json"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found — SEC raw data is cache-only")
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        manifest[f"{ticker}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        facts.extend(_parse_ticker(ticker, payload))
    return SecBundle(facts=tuple(facts), companies=tuple(tickers), manifest=manifest)


def _content_hash(row: dict) -> str:
    """SHA-256 over the exact raw source row (canonical JSON)."""
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _parse_ticker(ticker: str, payload: dict) -> list[SecFact]:
    facts: list[SecFact] = []
    seen: set[str] = set()
    for taxonomy, concepts in payload.get("facts", {}).items():
        for concept, meta in concepts.items():
            for unit, unit_facts in meta.get("units", {}).items():
                for fact in unit_facts:
                    form = fact.get("form")
                    if form not in TEMPORAL_FORMS:
                        continue
                    end = fact.get("end")
                    filed = fact.get("filed")
                    val = fact.get("val")
                    accn = fact.get("accn")
                    if not end or not filed or not isinstance(val, (int, float)) or not accn:
                        continue
                    # fact_id uniquely points to one raw source row: issuer,
                    # taxonomy, concept, unit, period, form, accession.
                    fact_id = (
                        f"{ticker}:{taxonomy}:{concept}:{unit}:"
                        f"{fact.get('start') or ''}:{end}:{form}:{accn}"
                    )
                    if fact_id in seen:
                        continue
                    seen.add(fact_id)
                    start = fact.get("start")
                    facts.append(SecFact(
                        fact_id=fact_id,
                        ticker=ticker,
                        taxonomy=taxonomy,
                        concept=concept,
                        value=float(val),
                        unit=unit,
                        start=_parse_date(start) if start else None,
                        end=_parse_date(end),
                        filed=_parse_date(filed),
                        accession=accn,
                        form=form,
                        fiscal_year=fact.get("fy"),
                        fiscal_period=fact.get("fp"),
                        frame=fact.get("frame"),
                        dimensions=None,  # companyfacts does not expose segment axes
                        scope=None,       # NOT auto-"consolidated"; only if known
                        content_hash=_content_hash(fact),
                    ))
    return facts
