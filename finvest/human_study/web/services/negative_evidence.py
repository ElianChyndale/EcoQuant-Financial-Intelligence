"""Negative-evidence protocol (Phase 7).

An auto-generated "insufficient" case is NOT a gold ABSTAIN. It is only a
``NO_EXACT_STRUCTURED_MATCH_CANDIDATE`` until a human-audited
``NegativeEvidenceCertificate`` exists. The certificate records the search
scope, query terms, document collection, cutoff, the fact that nothing was
found, and the human reviewer.

A negative case may only enter the annotation queue as
``READY_NEGATIVE_VERIFIED`` once the certificate is signed by a human.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# The 7 required search dimensions before a negative can be certified.
REQUIRED_SEARCHES = (
    "exact_concept_search",
    "semantic_alias_search",
    "taxonomy_migration_search",
    "full_allowed_filing_corpus_search",
    "filing_type_search",
    "period_and_unit_variants",
)


@dataclass(frozen=True)
class NegativeEvidenceCertificate:
    case_id: str
    search_scope: str
    query_terms: tuple[str, ...]
    document_collection: tuple[str, ...]
    source_cutoff: str
    not_found_statement: str
    human_reviewer: str
    searches_performed: tuple[str, ...]
    signed: bool = False
    timestamp: str | None = None


def new_certificate(
    *,
    case_id: str,
    query_terms: tuple[str, ...],
    document_collection: tuple[str, ...],
    source_cutoff: str,
    human_reviewer: str,
) -> NegativeEvidenceCertificate:
    """Create an unsigned certificate draft (researcher signs it)."""
    return NegativeEvidenceCertificate(
        case_id=case_id,
        search_scope="; ".join(REQUIRED_SEARCHES),
        query_terms=query_terms,
        document_collection=document_collection,
        source_cutoff=source_cutoff,
        not_found_statement="No fact found across the required search dimensions.",
        human_reviewer=human_reviewer,
        searches_performed=REQUIRED_SEARCHES,
    )


def sign_certificate(
    cert: NegativeEvidenceCertificate, *, reviewer_id: str
) -> NegativeEvidenceCertificate:
    """Sign the certificate (human only; must match the reviewer)."""
    if cert.human_reviewer != reviewer_id:
        raise ValueError("certificate reviewer does not match the signer")
    return NegativeEvidenceCertificate(
        **{**cert.__dict__,
           "signed": True,
           "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    )


def is_verified_negative(cert: NegativeEvidenceCertificate | None) -> bool:
    return cert is not None and cert.signed


def save_certificate(cert: NegativeEvidenceCertificate, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(cert.__dict__, sort_keys=True, default=str) + "\n")
    return path
