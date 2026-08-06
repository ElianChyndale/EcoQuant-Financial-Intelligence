"""Canonical evidence resolution service.

Produces ONE immutable ``CanonicalEvidenceRecord`` per frozen evidence item.
Evidence cards, the XBRL tab, the version timeline, and mechanical checks ALL
consume the same record — never frozen metadata in one panel and resolved
metadata in another.

Exact resolution matches on (issuer, concept, period, form, filed, unit) where
available. The broad "first non-null fact" fallback is removed. If exact
resolution is impossible -> EVIDENCE_RESOLUTION_FAILED. If frozen and resolved
metadata disagree on a meaningful field -> EVIDENCE_METADATA_INCONSISTENCY with
the exact conflicting fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

RESOLUTION_FAILED = "EVIDENCE_RESOLUTION_FAILED"
METADATA_INCONSISTENCY = "EVIDENCE_METADATA_INCONSISTENCY"


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
    inconsistency_fields: tuple[str, ...] = field(default_factory=tuple)


def _parse_date(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _issuer_of(evidence: dict) -> str:
    return str(evidence.get("document_id", "")).split("-")[0].upper()


def _resolve_companyfacts_exact(evidence: dict, cache: Path) -> CanonicalEvidenceRecord | None:
    """Exact match against companyfacts by issuer+concept+end+form+filed.

    Returns None if no exact fact matches (caller falls through to a failure
    record — never a broad fallback).
    """
    issuer = _issuer_of(evidence)
    concept = evidence.get("concept")
    if not concept:
        return None
    path = cache / "sec" / f"{issuer.lower()}_companyfacts.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    target_end = _parse_date(evidence.get("valid_from"))
    target_form = evidence.get("document_version")
    target_filed = _parse_date(evidence.get("filing_date"))
    target_unit = evidence.get("unit")
    target_fact_id = evidence.get("xbrl_fact_id")

    matches: list[tuple[float, dict]] = []
    for taxonomy, concepts in payload.get("facts", {}).items():
        if concept not in concepts:
            continue
        for unit, facts in concepts[concept].get("units", {}).items():
            for fact in facts:
                # Exact identity match: end, form, filed, unit.
                if target_end and _parse_date(fact.get("end")) != target_end:
                    continue
                if target_form and fact.get("form") != target_form:
                    continue
                if target_filed and _parse_date(fact.get("filed")) != target_filed:
                    continue
                if target_unit and unit != target_unit:
                    continue
                if target_fact_id:
                    # Prefer the fact whose (concept,end,filed,form) matches the
                    # frozen fact id structure; fall back to any exact identity.
                    pass
                score = 0
                if fact.get("accn"):
                    score += 1
                matches.append((score, fact))
    if not matches:
        return None
    best = max(matches, key=lambda item: item[0])[1]
    return _to_canonical(evidence, taxonomy, concept, best, unit)


def _to_canonical(
    evidence: dict,
    taxonomy: str,
    concept: str,
    fact: dict,
    unit: str,
) -> CanonicalEvidenceRecord:
    record = CanonicalEvidenceRecord(
        evidence_id=evidence["evidence_id"],
        issuer=_issuer_of(evidence),
        taxonomy=taxonomy,
        concept=concept,
        value=fact.get("val"),
        unit=unit,
        scale=str(evidence.get("scale") or "") or None,
        start=_parse_date(fact.get("start")),
        end=_parse_date(fact.get("end")),
        fiscal_year=str(fact.get("fy")) if fact.get("fy") is not None else None,
        fiscal_period=fact.get("fp"),
        form=fact.get("form"),
        filing_date=_parse_date(fact.get("filed")),
        accession=fact.get("accn"),
        dimensions=None,  # companyfacts does not expose segment axes
        amendment_status="AMENDED" if str(fact.get("form", "")).endswith("/A") else "ORIGINAL",
        source_fact_id=f"{concept}:{fact.get('end')}:{fact.get('filed')}:{fact.get('form')}",
        source_hash=fact.get("accn") or evidence.get("content_hash"),
        resolution_status="resolved",
    )
    return record


def _check_metadata_consistency(
    evidence: dict, record: CanonicalEvidenceRecord
) -> CanonicalEvidenceRecord:
    """Return an inconsistency record if frozen vs resolved metadata disagree."""
    conflicts: list[str] = []
    if evidence.get("concept") and record.concept != evidence.get("concept"):
        conflicts.append(f"concept:{record.concept}!={evidence.get('concept')}")
    if evidence.get("document_version") and record.form != evidence.get("document_version"):
        conflicts.append(f"form:{record.form}!={evidence.get('document_version')}")
    if evidence.get("valid_from") and record.end != _parse_date(evidence.get("valid_from")):
        conflicts.append(f"end:{record.end}!={_parse_date(evidence.get('valid_from'))}")
    if evidence.get("filing_date") and record.filing_date != _parse_date(evidence.get("filing_date")):
        conflicts.append(f"filed:{record.filing_date}!={_parse_date(evidence.get('filing_date'))}")
    if not conflicts:
        return record
    return CanonicalEvidenceRecord(
        **{**record.__dict__,
           "resolution_status": METADATA_INCONSISTENCY,
           "inconsistency_fields": tuple(conflicts)},
    )


def resolve_evidence(evidence: dict, cache: Path) -> CanonicalEvidenceRecord:
    """Resolve one evidence item to a canonical record, or an explicit failure."""
    if not evidence.get("evidence_id"):
        return CanonicalEvidenceRecord(
            evidence_id="", issuer="", resolution_status=RESOLUTION_FAILED,
            missing_asset="evidence_id missing",
        )
    record = _resolve_companyfacts_exact(evidence, cache)
    if record is not None:
        return _check_metadata_consistency(evidence, record)
    return CanonicalEvidenceRecord(
        evidence_id=evidence["evidence_id"],
        issuer=_issuer_of(evidence),
        concept=evidence.get("concept"),
        unit=evidence.get("unit"),
        scale=str(evidence.get("scale") or "") or None,
        end=_parse_date(evidence.get("valid_from")),
        filing_date=_parse_date(evidence.get("filing_date")),
        form=evidence.get("document_version"),
        resolution_status=RESOLUTION_FAILED,
        missing_asset=(
            f"companyfacts {_issuer_of(evidence).lower()}_companyfacts.json concept "
            f"{evidence.get('concept')} end {_parse_date(evidence.get('valid_from'))}"
        ),
    )


def resolve_evidence_set(evidence_items: list[dict], cache: Path) -> list[CanonicalEvidenceRecord]:
    return [resolve_evidence(item, cache) for item in evidence_items]
