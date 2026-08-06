"""Workbench data models (view projections; no annotation semantics)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceViewRow:
    evidence_id: str
    concept: str
    document_version: str
    filing_date: str
    unit: str | None
    scale: str | None
    resolution_status: str
    text_excerpt: str | None = None


@dataclass(frozen=True)
class CaseContext:
    queue: str
    key: str
    question: str
    issuer: str | None
    source_cutoff: str | None
    target_period: str | None
    evidence: tuple[EvidenceViewRow, ...] = field(default_factory=tuple)
