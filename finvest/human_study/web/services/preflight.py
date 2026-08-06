"""Case usability preflight — 4-state classification (Phase 7).

States:

- READY_POSITIVE — evidence resolves uniquely; the researcher can see the
  requested metric, value, unit, period, issuer, filing date, form, accession,
  and original source.
- READY_NEGATIVE_VERIFIED — a negative case backed by a human-signed
  NegativeEvidenceCertificate.
- TOOLING_BLOCKED — evidence cannot be resolved (zero/ambiguous), metadata is
  inconsistent, or a negative case lacks a verified certificate.
- SCIENTIFICALLY_INVALID — the frozen case itself is invalid (cross-concept
  version relation, bad chronology).

A TOOLING_BLOCKED or SCIENTIFICALLY_INVALID case must NOT be signable.
An auto-generated "insufficient" case without a certificate is NOT ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .evidence_service import (
    AMBIGUOUS_IDENTITY,
    METADATA_INCONSISTENCY,
    RESOLUTION_FAILED,
    CanonicalEvidenceRecord,
    resolve_evidence_set,
)
from .negative_evidence import is_verified_negative

READY_POSITIVE = "READY_POSITIVE"
READY_NEGATIVE_VERIFIED = "READY_NEGATIVE_VERIFIED"
BLOCKED = "TOOLING_BLOCKED"
INVALID = "SCIENTIFICALLY_INVALID"

READY_STATES = {READY_POSITIVE, READY_NEGATIVE_VERIFIED}


@dataclass(frozen=True)
class CasePreflight:
    case_id: str
    queue: str
    status: str
    reason: str | None = None
    evidence_statuses: tuple[str, ...] = field(default_factory=tuple)


def _positive_evidence_ready(records: tuple[CanonicalEvidenceRecord, ...]) -> bool:
    """READY_POSITIVE requires EVERY evidence item resolved uniquely."""
    return bool(records) and all(r.resolution_status == "resolved" for r in records)


def _version_relation_valid(case: dict) -> bool:
    relations = case.get("version_relations", [])
    if not relations:
        return True
    by_id = {ev["evidence_id"]: ev for ev in case.get("evidence_items", [])}
    for relation in relations:
        source = by_id.get(relation.get("source_document"))
        target = by_id.get(relation.get("target_document"))
        if source is None or target is None:
            return False
        if source.get("concept") != target.get("concept"):
            return False
        try:
            from datetime import date

            if date.fromisoformat(str(target.get("filing_date"))) < date.fromisoformat(str(source.get("filing_date"))):
                return False
        except (ValueError, TypeError):
            return False
    return True


def preflight_case(
    case: dict,
    *,
    queue: str,
    cache: Path,
    negative_certificates: dict[str, object] | None = None,
    tickers: tuple[str, ...] | None = None,
) -> CasePreflight:
    """Classify one frozen case into one of the four states."""
    records = resolve_evidence_set(
        case.get("evidence_items", []), cache, tickers=tickers
    )
    statuses = tuple(r.resolution_status for r in records)

    # SCIENTIFICALLY_INVALID: broken version relation.
    if not _version_relation_valid(case):
        return CasePreflight(case["case_id"], queue, INVALID,
                             reason="invalid version relation (cross-concept or bad chronology)",
                             evidence_statuses=statuses)

    # Negative (insufficient) case: READY only with a verified certificate.
    if case.get("answer_type") == "unanswerable" or not case.get("evidence_items"):
        cert = (negative_certificates or {}).get(case["case_id"])
        if is_verified_negative(cert):
            return CasePreflight(case["case_id"], queue, READY_NEGATIVE_VERIFIED,
                                 evidence_statuses=statuses)
        return CasePreflight(
            case["case_id"], queue, BLOCKED,
            reason="negative case without human-audited NegativeEvidenceCertificate",
            evidence_statuses=statuses,
        )

    # Positive case: every evidence item must resolve uniquely.
    if not _positive_evidence_ready(records):
        failed = [r.missing_asset for r in records if r.resolution_status == RESOLUTION_FAILED]
        inconsistent = [r.inconsistency_fields for r in records if r.resolution_status == METADATA_INCONSISTENCY]
        ambiguous = [r.missing_asset for r in records if r.resolution_status == AMBIGUOUS_IDENTITY]
        reason = "evidence resolution incomplete"
        if failed:
            reason += f"; missing: {failed[0]}"
        if inconsistent:
            reason += f"; inconsistent: {inconsistent[0]}"
        if ambiguous:
            reason += f"; ambiguous: {ambiguous[0]}"
        return CasePreflight(case["case_id"], queue, BLOCKED,
                             reason=reason, evidence_statuses=statuses)

    return CasePreflight(case["case_id"], queue, READY_POSITIVE, evidence_statuses=statuses)


def preflight_queues(
    manifest: dict, *, cache: Path, negative_certificates: dict[str, object] | None = None,
    tickers: tuple[str, ...] | None = None,
) -> dict[str, dict[str, list[str]]]:
    counts: dict[str, dict[str, list[str]]] = {
        READY_POSITIVE: [], READY_NEGATIVE_VERIFIED: [], BLOCKED: [], INVALID: [],
    }
    for case in manifest["sealed"].get("base_22_queue", []):
        result = preflight_case(case, queue="base", cache=cache,
                                negative_certificates=negative_certificates,
                                tickers=tickers)
        counts[result.status].append(case["case_id"])
    return counts
