"""FinVEST-Bench gold schemas (frozen per PREREGISTRATION).

Defines the benchmark case schema: requirement graph, evidence items,
acceptable/minimal evidence sets, calculation programs, version relations,
and decision/sufficiency labels. Typed dataclasses with validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class RequirementNode:
    """One node in the question requirement graph."""

    node_id: str
    node_type: str  # ENTITY | METRIC | PERIOD | UNIT | SCALE | SCOPE | DOCUMENT_TYPE | VERSION | OPERATION | INTERMEDIATE_VALUE | FINAL_VALUE
    value: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RequirementEdge:
    """Directed edge between requirement nodes."""

    source_id: str
    target_id: str
    relation: str  # REQUIRES | DERIVES_FROM | SAME_AS | CONTRADICTS | SUPERSEDES


@dataclass(frozen=True)
class RequirementGraph:
    nodes: tuple[RequirementNode, ...]
    edges: tuple[RequirementEdge, ...]

    def validate(self) -> None:
        ids = {n.node_id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("duplicate requirement node ids")
        for edge in self.edges:
            if edge.source_id not in ids or edge.target_id not in ids:
                raise ValueError(f"edge references unknown node: {edge}")


@dataclass(frozen=True)
class EvidenceItem:
    """One evidence unit (page/table/cell/XBRL fact) with full provenance."""

    evidence_id: str
    document_id: str
    document_version: str
    filing_date: date
    valid_from: date | None = None
    valid_to: date | None = None
    page_id: str | None = None
    section: str | None = None
    table_id: str | None = None
    row: int | None = None
    column: int | None = None
    text_span: str | None = None
    xbrl_fact_id: str | None = None
    concept: str | None = None
    unit: str | None = None
    scale: str | None = None
    scope: str | None = None
    content_hash: str | None = None
    fiscal_year: int | None = None  # original filing's fiscal-year label (disambiguates comparatives)


@dataclass(frozen=True)
class CalculationProgram:
    """Executable program for a derived numerical answer."""

    operation: str  # subtract | add | multiply | divide | average | ...
    inputs: tuple[str, ...]  # metric names referencing evidence items
    result: float
    unit: str | None = None
    scale: str | None = None
    period: str | None = None


@dataclass(frozen=True)
class VersionRelation:
    """Document-version relation (amendment / supersession)."""

    source_document: str
    target_document: str
    relation: str  # SUPERSEDES | AMENDS | SAME_FILING_DIFFERENT_FORMAT


@dataclass(frozen=True)
class FinVestCase:
    """One benchmark case with gold labels and evidence sets."""

    case_id: str
    base_question_id: str
    issuer_id: str
    jurisdiction: str  # US | EU | OTHER
    question: str
    source_cutoff: datetime
    target_period_start: date | None
    target_period_end: date | None
    target_fiscal_year: str | None
    answer_type: str  # extractive | derived | comparative | unanswerable
    gold_answer: dict[str, object] = field(default_factory=dict)
    decision_label: str = ""  # ANSWER | REVIEW | ABSTAIN
    sufficiency_label: str = ""  # SUPPORTED | PARTIAL | REFUTED | CONFLICTING | INSUFFICIENT
    requirement_graph: RequirementGraph | None = None
    acceptable_evidence_sets: tuple[frozenset[str], ...] = ()
    minimal_evidence_sets: tuple[frozenset[str], ...] = ()
    evidence_items: tuple[EvidenceItem, ...] = ()
    calculation_program: CalculationProgram | None = None
    assumptions: tuple[str, ...] = ()
    known_conflicts: tuple[str, ...] = ()
    version_relations: tuple[VersionRelation, ...] = ()
    prohibited_claims: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.case_id or not self.question:
            raise ValueError("case requires case_id and question")
        if self.decision_label not in {"ANSWER", "REVIEW", "ABSTAIN"}:
            raise ValueError(f"invalid decision_label: {self.decision_label}")
        if self.sufficiency_label not in {
            "SUPPORTED", "PARTIAL", "REFUTED", "CONFLICTING", "INSUFFICIENT",
        }:
            raise ValueError(f"invalid sufficiency_label: {self.sufficiency_label}")
        if self.requirement_graph is not None:
            self.requirement_graph.validate()
        if self.answer_type not in {"extractive", "derived", "comparative", "unanswerable"}:
            raise ValueError(f"invalid answer_type: {self.answer_type}")
        # Every evidence set must reference known evidence items.
        known = {e.evidence_id for e in self.evidence_items}
        for evidence_set in (*self.acceptable_evidence_sets, *self.minimal_evidence_sets):
            unknown = evidence_set - known
            if unknown:
                raise ValueError(f"evidence set references unknown items: {sorted(unknown)}")


# Paired evidence conditions (per PREREGISTRATION + codex spec).
EVIDENCE_CONDITIONS = (
    "FULL",
    "PARTIAL_MISSING_INPUT",
    "OUTDATED",
    "FUTURE_LEAK",
    "WRONG_PERIOD",
    "WRONG_SCOPE",
    "CONFLICTING",
    "REFUTED",
    "DISTRACTOR",
    "OCR_OR_LAYOUT_NOISE",
)

# Alias matching the programme's FinVEST branding.
FinVESTCase = FinVestCase
