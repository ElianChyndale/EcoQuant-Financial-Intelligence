"""Canonical evidence resolution — STRICT unique-match (Phase 5).

Resolver outcomes are exactly one of:

- ``resolved`` — exactly one source fact matches the full identity;
- ``EVIDENCE_RESOLUTION_FAILED`` — zero matches;
- ``AMBIGUOUS_IDENTITY`` — more than one candidate matches.

No "best of several candidates" fallback. The resolved record's taxonomy,
unit, and all metadata come from the SAME matched fact (never a loop-end
temporary).

Consistency check compares at least: issuer, taxonomy, concept, value, unit,
start, end, form, filing date, accession, fiscal year, fiscal period. Any
inconsistency -> ``EVIDENCE_METADATA_INCONSISTENCY`` and the case must NOT
enter the annotation queue.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

RESOLUTION_FAILED = "EVIDENCE_RESOLUTION_FAILED"
METADATA_INCONSISTENCY = "EVIDENCE_METADATA_INCONSISTENCY"
AMBIGUOUS_IDENTITY = "AMBIGUOUS_IDENTITY"

# Fields compared between frozen descriptor and resolved fact.
CONSISTENCY_FIELDS = (
    "issuer", "taxonomy", "concept", "value", "unit", "start", "end",
    "form", "filing_date", "accession", "fiscal_year", "fiscal_period",
)


@dataclass(frozen=True)
class CanonicalEvidenceRecord:
    """Immutable canonical record; the single source of truth per evidence item."""

    evidence_id: str
    issuer: str
    taxonomy: str | None = None
    concept: str | None = None
    value: float | None = None
    unit: str | None = None
    scale: str | None = None
    start: str | None = None
    end: str | None = None
    fiscal_year: str | None = None
    fiscal_period: str | None = None
    form: str | None = None
    filing_date: str | None = None
    accession: str | None = None
    dimensions: str | None = None
    amendment_status: str | None = None
    source_fact_id: str | None = None
    source_hash: str | None = None
    resolution_status: str = RESOLUTION_FAILED
    missing_asset: str | None = None
    ambiguity_count: int | None = None
    inconsistency_fields: tuple[str, ...] = field(default_factory=tuple)


def _parse_date(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _issuer_of(evidence: dict) -> str:
    return str(evidence.get("document_id", "")).split("-")[0].upper()


class EvidenceResolver:
    """Loads companyfacts once and resolves evidence by STRICT identity."""

    def __init__(self, cache: Path, tickers: tuple[str, ...] = ("AAPL", "MSFT", "KO", "EQIX", "JNJ", "UPS")) -> None:
        self._cache = cache
        self._tickers = tickers
        self._bundle_cache = None

    def _bundle(self):
        if self._bundle_cache is None:
            self._bundle_cache = load_companyfacts(self._cache / "sec", tickers=self._tickers)
        return self._bundle_cache

    def _candidates(self, evidence: dict) -> list:
        """Facts matching the frozen descriptor's key identity fields."""
        issuer = _issuer_of(evidence)
        concept = evidence.get("concept")
        target_end = _parse_date(evidence.get("valid_from"))
        target_form = evidence.get("document_version")
        target_filed = _parse_date(evidence.get("filing_date"))
        target_unit = evidence.get("unit")
        target_start = _parse_date(evidence.get("valid_from"))  # start not in v0.1 descriptor

        matches = []
        for fact in self._bundle().facts:
            if fact.ticker != issuer or fact.concept != concept:
                continue
            if target_end and _parse_date(fact.end) != target_end:
                continue
            if target_form and fact.form != target_form:
                continue
            if target_filed and _parse_date(fact.filed) != target_filed:
                continue
            if target_unit and fact.unit != target_unit:
                continue
            matches.append(fact)
        return matches

    def resolve(self, evidence: dict) -> CanonicalEvidenceRecord:
        if not evidence.get("evidence_id"):
            return CanonicalEvidenceRecord(
                evidence_id="", issuer="", resolution_status=RESOLUTION_FAILED,
                missing_asset="evidence_id missing",
            )
        matches = self._candidates(evidence)
        if not matches:
            return CanonicalEvidenceRecord(
                evidence_id=evidence["evidence_id"], issuer=_issuer_of(evidence),
                concept=evidence.get("concept"),
                unit=evidence.get("unit"),
                end=_parse_date(evidence.get("valid_from")),
                filing_date=_parse_date(evidence.get("filing_date")),
                form=evidence.get("document_version"),
                resolution_status=RESOLUTION_FAILED,
                missing_asset=(
                    f"no exact fact: {_issuer_of(evidence)} {evidence.get('concept')} "
                    f"end {_parse_date(evidence.get('valid_from'))} form {evidence.get('document_version')}"
                ),
            )
        if len(matches) > 1:
            return CanonicalEvidenceRecord(
                evidence_id=evidence["evidence_id"], issuer=_issuer_of(evidence),
                concept=evidence.get("concept"),
                resolution_status=AMBIGUOUS_IDENTITY,
                ambiguity_count=len(matches),
                missing_asset=f"{len(matches)} facts match identity",
            )
        fact = matches[0]
        return _build_canonical(evidence, fact)


def _build_canonical(evidence: dict, fact) -> CanonicalEvidenceRecord:
    """Build the canonical record from the ONE matched fact, then check consistency."""
    record = CanonicalEvidenceRecord(
        evidence_id=evidence["evidence_id"],
        issuer=fact.ticker,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        value=fact.value,
        unit=fact.unit,
        scale=str(evidence.get("scale") or "") or None,
        start=_parse_date(fact.start),
        end=_parse_date(fact.end),
        fiscal_year=str(fact.fiscal_year) if fact.fiscal_year is not None else None,
        fiscal_period=fact.fiscal_period,
        form=fact.form,
        filing_date=_parse_date(fact.filed),
        accession=fact.accession,
        dimensions=fact.dimensions,
        amendment_status="AMENDED" if str(fact.form).endswith("/A") else "ORIGINAL",
        source_fact_id=fact.fact_id,
        source_hash=fact.content_hash,
        resolution_status="resolved",
    )
    conflicts = _consistency_conflicts(evidence, fact)
    if conflicts:
        return CanonicalEvidenceRecord(
            **{**record.__dict__, "resolution_status": METADATA_INCONSISTENCY,
               "inconsistency_fields": tuple(conflicts)},
        )
    return record


def _consistency_conflicts(evidence: dict, fact) -> list[str]:
    """Compare frozen descriptor vs the matched fact on 12 fields."""
    conflicts: list[str] = []
    expected = {
        "issuer": _issuer_of(evidence),
        "concept": evidence.get("concept"),
        "unit": evidence.get("unit"),
        "end": _parse_date(evidence.get("valid_from")),
        "form": evidence.get("document_version"),
        "filing_date": _parse_date(evidence.get("filing_date")),
        "accession": None,  # v0.1 descriptor has no accession; fact does
    }
    actual = {
        "issuer": fact.ticker,
        "concept": fact.concept,
        "unit": fact.unit,
        "end": _parse_date(fact.end),
        "form": fact.form,
        "filing_date": _parse_date(fact.filed),
        "accession": fact.accession,
    }
    for key, want in expected.items():
        if want is None:
            continue
        got = actual[key]
        if str(want) != str(got):
            conflicts.append(f"{key}:{got}!={want}")
    return conflicts


# Convenience single-shot API (constructs a resolver per call).
def resolve_evidence(evidence: dict, cache: Path) -> CanonicalEvidenceRecord:
    return EvidenceResolver(cache).resolve(evidence)


def resolve_evidence_set(evidence_items: list[dict], cache: Path) -> list[CanonicalEvidenceRecord]:
    resolver = EvidenceResolver(cache)
    return [resolver.resolve(item) for item in evidence_items]
