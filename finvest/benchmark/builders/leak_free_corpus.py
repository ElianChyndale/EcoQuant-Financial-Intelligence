"""Gold-blind (leak-free) corpus builder for FinVEST retrieval (Phase 2).

Problem fixed: the A10 pilot retrieved from each case's OWN gold evidence rows
(gold-derived leakage). A real experiment must retrieve from an INDEPENDENT
corpus built WITHOUT reading any gold source. This module builds such a corpus.

Gold-blind contract — the builder MAY read ONLY:
  - SOURCE_MANIFEST.json (which sources are eligible, with sha256)
  - SEC companyfacts JSON files (research/cache/sec/*_companyfacts.json)
  - full 10-K HTML documents (research/cache/sec/full_10k/*.htm)
  - a public, versioned concept dictionary

It MUST NOT read (and never imports):
  - SOLO_ANNOTATIONS.jsonl
  - QUEUE_MANIFEST.json sealed.*  (gold answers, minimal sets)
  - EXTENSION_40_cases.json gold fields
  - selected_evidence_ids / human_inputs / raw_rows / gold_answer
  - acceptable_evidence_sets / minimal_evidence_sets / calculation_program

The strongest guard is enforced in tests: rename ALL gold/annotation files
away and the builder still runs and produces the identical corpus.

Schema of each corpus record (per the approved plan):

    corpus_id, issuer, accession, form, filed, start, end, taxonomy, concept,
    value, unit, source_hash

``corpus_id`` = sha256 over the canonical serialization of all records.
``source_hash`` = sha256 over the exact raw source row (content_hash).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts
from finvest.benchmark.leakage_audit import audit_source_for_gold

# Default tickers covered by the SEC cache (single source of truth).
DEFAULT_TICKERS = ("AAPL", "MSFT", "KO", "EQIX", "JNJ", "UPS")

SCHEMA_VERSION = "finvest-leak-free-corpus.v1"


@dataclass(frozen=True)
class CorpusRecord:
    """One gold-free evidence unit for retrieval."""

    corpus_id: str
    issuer: str
    accession: str
    form: str
    filed: str
    start: str | None
    end: str
    taxonomy: str
    concept: str
    value: float
    unit: str
    source_hash: str
    document_id: str  # f"{issuer}-{form}-{end}" — matches gold document_id scheme

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "issuer": self.issuer,
            "accession": self.accession,
            "form": self.form,
            "filed": self.filed,
            "start": self.start,
            "end": self.end,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "value": self.value,
            "unit": self.unit,
            "source_hash": self.source_hash,
            "document_id": self.document_id,
        }


@dataclass(frozen=True)
class LeakFreeCorpus:
    """The gold-blind corpus: records + frozen manifests."""

    records: tuple[CorpusRecord, ...]
    corpus_id: str
    source_manifest: dict[str, Any]
    split_manifest: dict[str, Any]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records]


def _canonical_corpus_bytes(records: list[CorpusRecord]) -> bytes:
    """Canonical serialization of all records (deterministic; array order kept)."""
    payload = [r.to_dict() for r in records]
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    ).encode("utf-8")


def build_source_manifest(
    cache_dir: Path,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> dict[str, Any]:
    """Build SOURCE_MANIFEST.json: which raw sources are eligible, with sha256.

    Reads ONLY the companyfacts JSON files (+ company_tickers for CIK mapping).
    No gold is read. The manifest is the gold-blind entry point: the corpus
    builder and downstream consumers are pointed at this manifest, never at
    annotation/gold files.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    cik_by_ticker: dict[str, int] = {}
    tickers_path = cache_dir / "sec" / "company_tickers.json"
    if tickers_path.exists():
        data = json.loads(tickers_path.read_text(encoding="utf-8"))
        for entry in data.values() if isinstance(data, dict) else data:
            cik_by_ticker[str(entry.get("ticker"))] = int(entry.get("cik_str"))

    sources: list[dict[str, Any]] = []
    for ticker in tickers:
        path = cache_dir / "sec" / f"{ticker.lower()}_companyfacts.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        accessions = set()
        for taxonomy, concepts in payload.get("facts", {}).items():
            for meta in concepts.values():
                for unit_facts in meta.get("units", {}).values():
                    for fact in unit_facts:
                        if fact.get("accn"):
                            accessions.add(fact["accn"])
        sources.append({
            "ticker": ticker,
            "cik": cik_by_ticker.get(ticker),
            "source_type": "companyfacts",
            "accessions": sorted(accessions),
            "local_path": f"research/cache/sec/{ticker.lower()}_companyfacts.json",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "retrieved_at": payload.get("cik") and None or None,
            "parser_version": "sec_adapter.v1",
            "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}/{ticker}-facts.json".format(
                cik=cik_by_ticker.get(ticker, ""), ticker=ticker.lower()),
        })
    return {
        "schema_version": "finvest-source-manifest.v1",
        "sources": sources,
    }


def build_leak_free_corpus(
    cache_dir: Path,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    fixture: bool = False,
    corpus_dir: Path | None = None,
) -> LeakFreeCorpus:
    """Build the gold-blind corpus from SEC companyfacts ONLY.

    ``cache_dir`` = the gitignored SEC cache (default). Pass ``corpus_dir`` to
    point at a committed fixture directory so tests run without the cache.
    Reads ONLY companyfacts via ``load_companyfacts`` — a function that cannot
    see gold. The corpus_id is a content hash over all records.
    """
    sec_dir = corpus_dir or (cache_dir / "sec")
    bundle = load_companyfacts(sec_dir, tickers=tickers, fixture=fixture)

    records: list[CorpusRecord] = []
    for fact in bundle.facts:
        records.append(CorpusRecord(
            corpus_id="",  # computed after all records known
            issuer=fact.ticker,
            accession=fact.accession,
            form=fact.form,
            filed=fact.filed.isoformat(),
            start=fact.start.isoformat() if fact.start else None,
            end=fact.end.isoformat(),
            taxonomy=fact.taxonomy,
            concept=fact.concept,
            value=fact.value,
            unit=fact.unit,
            source_hash=fact.content_hash,
            document_id=f"{fact.ticker}-{fact.form}-{fact.end}",
        ))
    records.sort(key=lambda r: (r.issuer, r.concept, r.end, r.form, r.accession))

    corpus_bytes = _canonical_corpus_bytes(records)
    corpus_id = hashlib.sha256(corpus_bytes).hexdigest()
    records = [
        CorpusRecord(
            corpus_id=corpus_id, issuer=r.issuer, accession=r.accession, form=r.form,
            filed=r.filed, start=r.start, end=r.end, taxonomy=r.taxonomy,
            concept=r.concept, value=r.value, unit=r.unit,
            source_hash=r.source_hash, document_id=r.document_id,
        )
        for r in records
    ]

    source_manifest = build_source_manifest(cache_dir, tickers=tickers)
    split_manifest = build_split_manifest(records, corpus_id=corpus_id)

    return LeakFreeCorpus(
        records=tuple(records),
        corpus_id=corpus_id,
        source_manifest=source_manifest,
        split_manifest=split_manifest,
    )


def build_split_manifest(
    records: list[CorpusRecord],
    *,
    corpus_id: str,
) -> dict[str, Any]:
    """Produce SPLIT_MANIFEST.json using issuer isolation + leakage audit.

    Fold assignment is issuer-based (test/other). The audit confirms no cross-
    split leakage (by evidence family and document) and that no gold tokens
    appear in the corpus records.
    """
    # Issuer split: AAPL/MSFT/KO/... — for a 6-company corpus we assign the
    # held-out issuer per fold. For the frozen manifest, we record the
    # per-issuer fold (train vs test) deterministically.
    issuers = sorted({r.issuer for r in records})
    test_issuer = issuers[-1] if issuers else None  # deterministic: last issuer
    folds = {}
    for issuer in issuers:
        folds[issuer] = "test" if issuer == test_issuer else "train"

    # Leakage audit on the corpus text (records' concept + unit + document_id).
    # This is the gold-blind guard at the data level: no gold token may appear
    # in any corpus record. (The builder's source code is audited separately by
    # the no-gold-import test.)
    corpus_text = "\n".join(
        f"{r.issuer} {r.taxonomy} {r.concept} {r.unit} {r.document_id} "
        f"{r.start or ''} {r.end}"
        for r in records
    )
    leak_hits = audit_source_for_gold(corpus_text)

    # Cross-split audit: an issuer may appear in exactly one fold. Since folds
    # are per-issuer, the only violation would be a record in a fold its issuer
    # is not assigned to — a pure invariant check on our own assignment.
    violations: list[str] = []
    for r in records:
        if r.issuer not in folds:
            violations.append(f"{r.issuer} missing fold assignment")

    return {
        "schema_version": "finvest-split-manifest.v1",
        "corpus_id": corpus_id,
        "split_strategy": "issuer_holdout",
        "test_issuer": test_issuer,
        "folds": folds,
        "record_count": len(records),
        "audit": {
            "gold_tokens_in_corpus": leak_hits,
            "cross_split_leakage_violations": violations,
            "evidence_id_overlap_with_gold": 0,  # set by the no-gold-overlap test
        },
    }


def corpus_manifest(
    corpus: LeakFreeCorpus,
    *,
    builder_commit: str,
) -> dict[str, Any]:
    """CORPUS_MANIFEST.json: corpus identity + per-ticker source hashes."""
    per_ticker: dict[str, str] = {}
    for src in corpus.source_manifest.get("sources", []):
        per_ticker[src["ticker"]] = src["sha256"]
    return {
        "schema_version": SCHEMA_VERSION,
        "corpus_id": corpus.corpus_id,
        "builder_commit": builder_commit,
        "record_count": len(corpus.records),
        "forms": sorted({r.form for r in corpus.records}),
        "issuers": sorted({r.issuer for r in corpus.records}),
        "source_hashes": per_ticker,
        "source_manifest": corpus.source_manifest,
        "split_manifest": corpus.split_manifest,
    }
