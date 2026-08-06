"""Practice mode (Phase 10, redesigned in Phase 11).

A SEPARATE practice protocol. Practice judgements never enter formal results
or VISTA training.

ANTI-CONFIRMATION-BIAS FLOW: the practice page shows ONLY the Self-Contained
Human Evidence Package (definition, evidence table, time & version card,
independent calculation inputs). The reference answer and source explanation
are revealed ONLY AFTER the researcher submits their own judgement. The
researcher must complete >= 5 practice cases before the formal pilot starts.
Practice is not a signable flow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PRACTICE_REQUIRED_COUNT = 5


@dataclass(frozen=True)
class PracticeRecord:
    """One practice judgement (never a formal label).

    ``reference_answer`` / ``source_explanation`` are stored AFTER the
    researcher's own judgement is submitted (reveal-after-submit), so the
    stored record always captures the independent answer first.
    """

    practice_id: str
    case_id: str
    q1_answerable: str            # ANSWERABLE / PARTIAL / UNANSWERABLE / REVIEW
    q2_answer_and_calc: str       # the researcher's own answer + calculation
    q3_conflicts: str             # conflicts the researcher noticed
    your_calculation: str | None
    reference_answer: str         # revealed after submission
    source_explanation: str
    disagreement_reason: str | None
    reviewer_id: str
    timestamp: str


@dataclass(frozen=True)
class PracticeSummary:
    completed: int
    required: int
    ready: bool
    note: str


def record_practice(
    *,
    practice_path: Path,
    case_id: str,
    q1_answerable: str,
    q2_answer_and_calc: str,
    q3_conflicts: str,
    your_calculation: str | None,
    reference_answer: str,
    source_explanation: str,
    disagreement_reason: str | None,
    reviewer_id: str,
) -> PracticeRecord:
    """Store one practice record (explicitly NOT a human label)."""
    record = PracticeRecord(
        practice_id=f"practice-{case_id}",
        case_id=case_id,
        q1_answerable=q1_answerable,
        q2_answer_and_calc=q2_answer_and_calc,
        q3_conflicts=q3_conflicts,
        your_calculation=your_calculation,
        reference_answer=reference_answer,
        source_explanation=source_explanation,
        disagreement_reason=disagreement_reason,
        reviewer_id=reviewer_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    practice_path.parent.mkdir(parents=True, exist_ok=True)
    with practice_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.__dict__, sort_keys=True) + "\n")
    return record


def practice_summary(practice_path: Path) -> PracticeSummary:
    """Return completed/required/ready for the practice gate."""
    if not practice_path.exists():
        return PracticeSummary(0, PRACTICE_REQUIRED_COUNT, False,
                               "no practice cases completed")
    count = sum(1 for line in practice_path.read_text(encoding="utf-8").splitlines()
                if line.strip())
    return PracticeSummary(
        count, PRACTICE_REQUIRED_COUNT, count >= PRACTICE_REQUIRED_COUNT,
        "practice gate met" if count >= PRACTICE_REQUIRED_COUNT
        else f"{count}/{PRACTICE_REQUIRED_COUNT} practice cases completed",
    )
