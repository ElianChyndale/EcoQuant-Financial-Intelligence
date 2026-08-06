"""Case usability preflight (Phase 4).

Classifies every case before annotation:

- READY_FOR_ANNOTATION — the researcher can see requested metric, value, unit,
  period, issuer, filing date, form, accession/source id, and original source.
- TOOLING_BLOCKED — evidence cannot be resolved or metadata is inconsistent.
- INVALID_CASE — the frozen case itself is scientifically invalid (e.g. a
  version relation that pairs different concepts).

A TOOLING_BLOCKED or INVALID_CASE case must NOT be signable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .evidence_service import (
    METADATA_INCONSISTENCY,
    RESOLUTION_FAILED,
    CanonicalEvidenceRecord,
    resolve_evidence_set,
)

READY = "READY_FOR_ANNOTATION"
BLOCKED = "TOOLING_BLOCKED"
INVALID = "INVALID_CASE"


@dataclass(frozen=True)
class CasePreflight:
    case_id: str
    queue: str
    status: str  # READY | TOOLING_BLOCKED | INVALID
    reason: str | None = None
    evidence_statuses: tuple[str, ...] = field(default_factory=tuple)


def _evidence_sufficient(records: tuple[CanonicalEvidenceRecord, ...]) -> bool:
    """A case is READY only if EVERY evidence item resolved exactly."""
    return bool(records) and all(
        r.resolution_status == "resolved" for r in records
    )


def _version_relation_valid(case: dict) -> bool:
    """Version-aware case: original/amended timeline must be coherent."""
    relations = case.get("version_relations", [])
    if not relations:
        return True  # not a version-aware case
    by_id = {ev["evidence_id"]: ev for ev in case.get("evidence_items", [])}
    for relation in relations:
        source = by_id.get(relation.get("source_document"))
        target = by_id.get(relation.get("target_document"))
        if source is None or target is None:
            return False  # dangling relation
        if source.get("concept") != target.get("concept"):
            return False  # cross-concept amendment (v0.1 defect)
        try:
            from datetime import date

            if date.fromisoformat(str(target.get("filing_date"))) < date.fromisoformat(str(source.get("filing_date"))):
                return False  # amendment predates original
        except (ValueError, TypeError):
            return False
    return True


def preflight_case(case: dict, *, queue: str, cache: Path) -> CasePreflight:
    """Classify one frozen case."""
    records = resolve_evidence_set(case.get("evidence_items", []), cache)
    statuses = tuple(r.resolution_status for r in records)

    # INVALID: cross-concept or broken version relation.
    if not _version_relation_valid(case):
        return CasePreflight(case["case_id"], queue, INVALID,
                             reason="invalid version relation (cross-concept or bad chronology)",
                             evidence_statuses=statuses)

    # TOOLING_BLOCKED: evidence not fully resolved.
    if not _evidence_sufficient(records):
        failed = [r.missing_asset for r in records if r.resolution_status == RESOLUTION_FAILED]
        inconsistent = [
            r.inconsistency_fields for r in records
            if r.resolution_status == METADATA_INCONSISTENCY
        ]
        reason = "evidence resolution incomplete"
        if failed:
            reason += f"; missing: {failed[0]}"
        if inconsistent:
            reason += f"; inconsistent: {inconsistent[0]}"
        return CasePreflight(case["case_id"], queue, BLOCKED,
                             reason=reason, evidence_statuses=statuses)

    return CasePreflight(case["case_id"], queue, READY,
                         evidence_statuses=statuses)


def preflight_queues(
    manifest: dict, *, cache: Path
) -> dict[str, dict[str, list[str]]]:
    """Classify every base case; return {status: [case_ids]} for the dashboard."""
    counts: dict[str, dict[str, list[str]]] = {
        READY: [], BLOCKED: [], INVALID: [],
    }
    for case in manifest["sealed"].get("base_22_queue", []):
        result = preflight_case(case, queue="base", cache=cache)
        counts[result.status].append(case["case_id"])
    return counts
