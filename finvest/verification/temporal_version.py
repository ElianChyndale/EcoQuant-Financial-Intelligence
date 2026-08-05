"""FinVEST joint temporal + version verification (A4).

Fixes the E3 problem: constraints (source-time, valid-time, version) were
optimized separately, so contradiction-aware dedup raised the future rate.
This module applies them JOINTLY: an evidence set is time-valid only if EVERY
item satisfies source-time, valid-time, AND version constraints together.

Version relations: SUPERSEDES / AMENDS / SAME_FILING_DIFFERENT_FORMAT. A
superseded evidence item is invalid; an amended value is the latest valid one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import reduce

from finvest.benchmark.schemas import EvidenceItem, VersionRelation


@dataclass(frozen=True)
class TemporalVerification:
    """Joint temporal+version verification of an evidence set."""

    valid: bool
    future_information_rate: float  # items filed after source cutoff / total
    expired_evidence_rate: float    # items with valid_from after target end / total
    wrong_period_rate: float        # items whose valid_from is in a different fiscal year / total
    superseded_rate: float          # items superseded by a later version / total
    violations: tuple[str, ...]


def _source_time_ok(item: EvidenceItem, source_cutoff: datetime) -> bool:
    return item.filing_date <= source_cutoff.date()


def _valid_time_ok(item: EvidenceItem, target_end: date | None) -> bool:
    if target_end is None or item.valid_from is None:
        return True
    return item.valid_from <= target_end


def _wrong_period(item: EvidenceItem, target_fiscal_year: str | None) -> bool:
    if target_fiscal_year is None or item.valid_from is None:
        return False
    expected_year = target_fiscal_year.replace("FY", "")
    return str(item.valid_from.year) != expected_year


def _superseded(item: EvidenceItem, relations: tuple[VersionRelation, ...]) -> bool:
    """True if another document version supersedes this item's document."""
    return any(
        relation.source_document == item.document_id
        and relation.relation == "SUPERSEDES"
        for relation in relations
    )


def verify_joint_temporal(
    evidence: tuple[EvidenceItem, ...],
    *,
    source_cutoff: datetime,
    target_end: date | None,
    target_fiscal_year: str | None,
    version_relations: tuple[VersionRelation, ...] = (),
) -> TemporalVerification:
    """Jointly verify source-time, valid-time, period, and version constraints.

    Returns valid=False if ANY item violates any constraint (joint, not
    per-constraint optimization).
    """
    violations: list[str] = []
    total = len(evidence) or 1
    future = expired = wrong_period = superseded = 0

    for item in evidence:
        if not _source_time_ok(item, source_cutoff):
            future += 1
            violations.append(f"{item.evidence_id}: filed {item.filing_date} after cutoff {source_cutoff.date()}")
        if not _valid_time_ok(item, target_end):
            expired += 1
            violations.append(f"{item.evidence_id}: valid_from {item.valid_from} after target {target_end}")
        if _wrong_period(item, target_fiscal_year):
            wrong_period += 1
            violations.append(f"{item.evidence_id}: period {item.valid_from} not in {target_fiscal_year}")
        if _superseded(item, version_relations):
            superseded += 1
            violations.append(f"{item.evidence_id}: superseded by later version")

    return TemporalVerification(
        valid=not violations,
        future_information_rate=future / total,
        expired_evidence_rate=expired / total,
        wrong_period_rate=wrong_period / total,
        superseded_rate=superseded / total,
        violations=tuple(violations),
    )


def latest_valid_version(
    items: tuple[EvidenceItem, ...],
    version_relations: tuple[VersionRelation, ...],
) -> tuple[EvidenceItem, ...]:
    """Keep only the latest-valid version of each document (amendment-aware).

    When a document has an AMENDS relation, the amended (target) document's
    items win over the original's — the original's items are superseded.
    """
    superseded_docs = {
        relation.source_document
        for relation in version_relations
        if relation.relation == "SUPERSEDES" or relation.relation == "AMENDS"
    }
    return tuple(item for item in items if item.document_id not in superseded_docs)
