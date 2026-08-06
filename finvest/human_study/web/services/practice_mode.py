"""Practice mode (Phase 10).

A SEPARATE practice protocol. Practice judgements never enter formal results
or VISTA training. After a practice submission, the system may display the
reference answer, source explanation, and disagreement reason so the
researcher learns the judgement rules.

The researcher must complete >= 5 practice cases and be able to explain the
rules before the formal pilot starts. Practice is not a signable flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PRACTICE_REQUIRED_COUNT = 5


@dataclass(frozen=True)
class PracticeRecord:
    """One practice judgement (never a formal label)."""

    practice_id: str
    case_id: str
    researcher_judgement: str  # e.g. SUPPORTED / PARTIAL / ...
    reference_answer: str
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
    researcher_judgement: str,
    reference_answer: str,
    source_explanation: str,
    disagreement_reason: str | None,
    reviewer_id: str,
) -> PracticeRecord:
    """Store one practice record (explicitly NOT a human label)."""
    record = PracticeRecord(
        practice_id=f"practice-{case_id}",
        case_id=case_id,
        researcher_judgement=researcher_judgement,
        reference_answer=reference_answer,
        source_explanation=source_explanation,
        disagreement_reason=disagreement_reason,
        reviewer_id=reviewer_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    practice_path.parent.mkdir(parents=True, exist_ok=True)
    with practice_path.open("a", encoding="utf-8") as handle:
        import json

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
