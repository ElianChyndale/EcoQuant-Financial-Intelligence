"""Paired evidence-condition generator (PREREGISTRATION + codex spec).

Each base case is expanded into paired counterfactual instances that change
ONLY the evidence condition, keeping the question and candidate answer fixed.
This tests whether a system is sensitive to evidence changes rather than
learning shortcuts (SURE-RAG's counterfactual swaps, extended with financial
period/unit/version/calculation dimensions).

Conditions:
- FULL: all required evidence present and consistent.
- PARTIAL_MISSING_INPUT: one mandatory input removed.
- OUTDATED: old value kept, latest valid value removed.
- FUTURE_LEAK: evidence filed after the source cutoff added.
- WRONG_PERIOD: correct company/metric, wrong fiscal year.
- WRONG_SCOPE: group/segment, GAAP/non-GAAP, or continuing-ops scope wrong.
- CONFLICTING: original + amended coexist unresolved.
- REFUTED: evidence explicitly contradicts the candidate answer.
- DISTRACTOR: many semantically similar but irrelevant pages added.
- OCR_OR_LAYOUT_NOISE: table structure/units/page order perturbed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .schemas import EVIDENCE_CONDITIONS, EvidenceItem, FinVestCase


@dataclass(frozen=True)
class ConditionedInstance:
    """One base case under one evidence condition."""

    instance_id: str
    base_case_id: str
    condition: str
    question: str
    evidence_items: tuple[EvidenceItem, ...]
    source_cutoff: datetime
    gold_answer: dict[str, object]
    decision_label: str  # ANSWER | REVIEW | ABSTAIN
    sufficiency_label: str


def generate_conditions(
    case: FinVestCase,
    *,
    distractor_pool: tuple[EvidenceItem, ...] = (),
) -> tuple[ConditionedInstance, ...]:
    """Expand one base case into its paired evidence conditions."""
    instances: list[ConditionedInstance] = []
    base_evidence = case.evidence_items

    # FULL
    instances.append(_make(case, "FULL", base_evidence, case.decision_label, case.sufficiency_label))

    # PARTIAL_MISSING_INPUT: drop the last evidence item (a mandatory input).
    if len(base_evidence) >= 2:
        partial = base_evidence[:-1]
        instances.append(_make(case, "PARTIAL_MISSING_INPUT", partial, "REVIEW", "PARTIAL"))

    # OUTDATED: keep only the earliest-filed evidence (drop latest).
    if base_evidence:
        earliest = tuple(sorted(base_evidence, key=lambda e: e.filing_date)[:1])
        instances.append(_make(case, "OUTDATED", earliest, "REVIEW", "PARTIAL"))

    # FUTURE_LEAK: add an evidence item filed after the cutoff.
    if base_evidence and distractor_pool:
        leaked = base_evidence + (distractor_pool[0],)
        instances.append(_make(case, "FUTURE_LEAK", leaked, "REVIEW", "CONFLICTING"))

    # WRONG_PERIOD: keep evidence but shift filing dates to a different year.
    wrong_period = tuple(
        EvidenceItem(
            **{**e.__dict__,
               "valid_from": _shift_year(e.valid_from, -1),
               "filing_date": _shift_year(e.filing_date, -1)},
        )
        for e in base_evidence
    )
    instances.append(_make(case, "WRONG_PERIOD", wrong_period, "REVIEW", "PARTIAL"))

    # CONFLICTING: duplicate evidence with a different value (original+amended).
    if base_evidence:
        first = base_evidence[0]
        conflicting = base_evidence + (
            EvidenceItem(
                evidence_id=f"{first.evidence_id}-amended",
                document_id=first.document_id, document_version="10-K/A",
                filing_date=first.filing_date, valid_from=first.valid_from,
                concept=first.concept, unit=first.unit, scale=first.scale,
                scope=first.scope, content_hash=f"{first.content_hash}-a",
            ),
        )
        instances.append(_make(case, "CONFLICTING", conflicting, "REVIEW", "CONFLICTING"))

    # DISTRACTOR: prepend a semantically-similar but irrelevant evidence item.
    if distractor_pool:
        distracted = distractor_pool[:2] + base_evidence
        instances.append(_make(case, "DISTRACTOR", distracted, case.decision_label, case.sufficiency_label))

    # OCR_OR_LAYOUT_NOISE: perturb text spans (garbled numbers) but keep IDs.
    noisy = tuple(
        EvidenceItem(
            **{**e.__dict__,
               "text_span": (e.text_span or "") + " [OCR:0O1l ambiguous]",
               "content_hash": f"{e.content_hash}-noise"},
        )
        for e in base_evidence
    )
    instances.append(_make(case, "OCR_OR_LAYOUT_NOISE", noisy, "REVIEW", "PARTIAL"))

    return tuple(instances)


def _make(
    case: FinVestCase,
    condition: str,
    evidence: tuple[EvidenceItem, ...],
    decision: str,
    sufficiency: str,
) -> ConditionedInstance:
    return ConditionedInstance(
        instance_id=f"{case.case_id}::{condition}",
        base_case_id=case.case_id,
        condition=condition,
        question=case.question,
        evidence_items=evidence,
        source_cutoff=case.source_cutoff,
        gold_answer=case.gold_answer,
        decision_label=decision,
        sufficiency_label=sufficiency,
    )


def _shift_year(value: object, delta: int) -> object:
    """Shift a date by delta years (used for WRONG_PERIOD)."""
    if value is None:
        return None
    try:
        return value.replace(year=value.year + delta)
    except (AttributeError, ValueError):
        return value
