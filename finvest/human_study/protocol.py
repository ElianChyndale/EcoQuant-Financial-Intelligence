"""FinVEST human decision-utility study protocol (A9).

Builds the interface and analysis; human labels are entered and signed by
human reviewers — never fabricated by an LLM. AI prepares interfaces,
pre-annotations, candidate evidence, and validation checks only.

Design (frozen per PREREGISTRATION §8):
- 24-30 reviewers (finance/accounting, CFA-candidate, CS/AI backgrounds).
- 240 stratified cases; within-subject crossover; Latin-square
  counterbalancing; blind system identity; >=3 independent decisions/case.
- Conditions: A answer-only, B answer+top-k pages, C answer+VISTA package
  (minimal evidence set + requirement checklist + calculation trace +
  version/conflict report + review recommendation).
- Mixed-effects analysis (reviewer/question/issuer random effects).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

CONDITIONS = ("A", "B", "C")
BACKGROUNDS = ("finance_accounting", "cfa_candidate", "cs_ai")


class Condition(Enum):
    A = "answer_only"
    B = "answer_topk_pages"
    C = "answer_vista_package"


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    question: str
    condition: Condition
    candidate_answer: str
    evidence_pages: tuple[str, ...] = ()
    vista_package: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewLabel:
    """One human reviewer's judgment (human-signed, never LLM)."""

    review_id: str
    case_id: str
    reviewer_id: str
    condition: str  # A | B | C
    answer_correct: bool
    evidence_sufficient: bool
    citation_correct: bool
    material_factor_missing: bool
    unsafe_acceptance: bool
    review_time_seconds: float
    reviewer_confidence: float  # 1-5
    error_category: str | None = None
    signed: bool = False  # must be True (human signature)


def latin_square(condition_order: list[Condition], reviewer_index: int) -> list[Condition]:
    """Latin-square counterbalancing of condition order per reviewer."""
    n = len(condition_order)
    offset = reviewer_index % n
    return condition_order[offset:] + condition_order[:offset]


def assign_cases(
    cases: list[ReviewCase],
    reviewer_id: str,
    reviewer_index: int,
    *,
    cases_per_reviewer: int = 40,
) -> list[ReviewCase]:
    """Assign a balanced subset of cases to one reviewer (stratified)."""
    # Stratify by condition value, take every reviewer_index-th slice.
    by_condition: dict[str, list[ReviewCase]] = {}
    for case in cases:
        by_condition.setdefault(case.condition.value, []).append(case)
    assigned: list[ReviewCase] = []
    condition_values = [c.value for c in Condition]
    per_condition = cases_per_reviewer // len(condition_values)
    for condition_value in condition_values:
        pool = by_condition.get(condition_value, [])
        if not pool:
            continue
        start = (reviewer_index * per_condition) % len(pool)
        assigned.extend(pool[start:start + per_condition])
    return assigned


def mixed_effects_summary(
    labels: list[ReviewLabel],
) -> dict[str, object]:
    """Aggregate human-study outcomes (descriptive; full mixed-effects model
    is fitted in the analysis milestone with statsmodels).

    Primary outcomes: final correctness, unsafe acceptance rate, material
    omission detection, wrong-period detection, calculation-error detection,
    review time. Secondary: confidence, confidence calibration, correction
    rate, perceived workload.
    """
    n = len(labels)
    if n == 0:
        return {"n_reviews": 0}
    by_condition: dict[str, list[ReviewLabel]] = {}
    for label in labels:
        by_condition.setdefault(label.condition, []).append(label)
    return {
        "n_reviews": n,
        "by_condition": {
            cond: {
                "n": len(cond_labels),
                "unsafe_acceptance_rate": sum(l.unsafe_acceptance for l in cond_labels) / len(cond_labels),
                "answer_correct_rate": sum(l.answer_correct for l in cond_labels) / len(cond_labels),
                "material_omission_detected_rate": sum(l.material_factor_missing for l in cond_labels) / len(cond_labels),
                "median_review_time_seconds": sorted(l.review_time_seconds for l in cond_labels)[len(cond_labels) // 2],
                "mean_confidence": sum(l.reviewer_confidence for l in cond_labels) / len(cond_labels),
            }
            for cond, cond_labels in by_condition.items()
        },
    }


def verify_labels_are_human(labels: list[ReviewLabel]) -> list[str]:
    """Return violations: labels that are not human-signed."""
    return [l.review_id for l in labels if not l.signed]
