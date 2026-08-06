"""Solo provisional annotation records (Phase 13).

Append-only JSONL per (protocol, queue). Every annotation is an independent
record: never overwritten, never deleted. Each record captures the raw human
judgements (Q1-Q5), the evidence package hash, the machine-derived labels
(separate from human choices), and the provisional status.

A future annotator can replay the SAME evidence package (by hash) and produce
an independent record; the comparison layer (reviewer_01 vs reviewer_02) is a
separate step.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finvest.human_study.solo_protocol import (
    CONFIDENCE_HIGH,
    PROTOCOL_VERSION,
    Q1_AMBIGUOUS,
    Q1_CLEAR,
    Q1_INVALID,
    STATUS_SOLO_PROVISIONAL,
    SUFFICIENCY_MAP,
    EVIDENCE_CONFLICTING,
    EVIDENCE_ENOUGH,
    EVIDENCE_NOT_ENOUGH,
    EVIDENCE_PARTLY,
    ROUTE_ANSWER,
    ROUTE_REVIEW,
    ROUTE_ABSTAIN,
    status_for_route,
)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SoloAnnotation:
    """One append-only solo annotation record."""

    case_id: str
    evidence_package_version: str
    evidence_package_hash: str
    annotation_protocol_version: str
    reviewer_id: str
    annotation_round: int
    question_clarity: str            # Q1: CLEAR / AMBIGUOUS / INVALID
    evidence_judgement: str          # Q2: ENOUGH / PARTLY / CONFLICTING / NOT_ENOUGH
    selected_evidence_ids: tuple[str, ...]
    human_inputs: dict[str, Any]     # Q3: input1/input2/formula
    human_answer: Any                # Q3: calculated answer
    issue_flags: tuple[str, ...]     # Q4 checkboxes
    route: str                       # Q5: ANSWER / REVIEW / ABSTAIN
    confidence: str                  # HIGH / MEDIUM / LOW
    rationale: str
    duration_seconds: int
    # Machine-derived (kept SEPARATE from human raw choices).
    derived: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_SOLO_PROVISIONAL
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    signed_record_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "evidence_package_version": self.evidence_package_version,
            "evidence_package_hash": self.evidence_package_hash,
            "annotation_protocol_version": self.annotation_protocol_version,
            "reviewer_id": self.reviewer_id,
            "annotation_round": self.annotation_round,
            "question_clarity": self.question_clarity,
            "evidence_judgement": self.evidence_judgement,
            "selected_evidence_ids": list(self.selected_evidence_ids),
            "human_inputs": self.human_inputs,
            "human_answer": self.human_answer,
            "issue_flags": list(self.issue_flags),
            "route": self.route,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "duration_seconds": self.duration_seconds,
            "derived": self.derived,
            "status": self.status,
            "created_at": self.created_at,
            "signed_record_hash": self.signed_record_hash,
        }


def derive_labels(
    q1: str,
    q2: str,
    *,
    issue_flags: tuple[str, ...],
    route: str,
    calc_mismatch: bool = False,
) -> dict[str, Any]:
    """Map raw human choices to research labels (kept separate from raw)."""
    question_valid = {
        Q1_CLEAR: "VALID", Q1_AMBIGUOUS: "AMBIGUOUS", Q1_INVALID: "INVALID",
    }.get(q1, "REVIEW_UNRESOLVED")
    answerability = "ANSWERABLE" if q1 == Q1_CLEAR else ("UNANSWERABLE" if q1 == Q1_INVALID else "REVIEW_UNRESOLVED")
    sufficiency = SUFFICIENCY_MAP.get(q2, "REVIEW_UNRESOLVED")
    if calc_mismatch and route == ROUTE_ANSWER:
        route = ROUTE_REVIEW
    return {
        "question_valid": question_valid,
        "answerability": answerability,
        "sufficiency": sufficiency,
        "route": route,
        "source_time_valid": None,
        "version_valid": None,
        "calculation_reproducible": not calc_mismatch,
    }


def append_annotation(
    path: Path,
    annotation: SoloAnnotation,
) -> SoloAnnotation:
    """Append one annotation record (never overwrite). Returns it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(annotation.as_dict(), sort_keys=True, default=str) + "\n")
    return annotation


def load_annotations(path: Path) -> list[dict[str, Any]]:
    """Load all annotation records (append-only; oldest first)."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"__malformed__": line})
    return out


def latest_annotation(path: Path, case_id: str) -> dict[str, Any] | None:
    """Most recent annotation for a case (records are append-only)."""
    latest = None
    for rec in load_annotations(path):
        if rec.get("case_id") == case_id:
            latest = rec
    return latest


# ---------------------------------------------------------------------------
# Delayed self re-check (Stage 5): compare round 1 vs round 2.
# ---------------------------------------------------------------------------

def compare_rounds(round1: dict[str, Any], round2: dict[str, Any]) -> dict[str, Any]:
    """Compare two annotation rounds of the SAME case by the SAME reviewer.

    Returns agreement on question/evidence/numeric/route/label plus the
    solo status per the protocol:
      - SOLO_CONFIRMED          both rounds agree on answer + route
      - SOLO_MINOR_DISAGREEMENT answer agrees, labels differ slightly
      - NEEDS_EXTERNAL_REVIEW   answer, evidence or route disagree
    """
    def num(a):
        try:
            return float(str(a).replace(",", "").replace(" ", ""))
        except (ValueError, TypeError):
            return None

    a1, a2 = num(round1.get("human_answer")), num(round2.get("human_answer"))
    numeric_agree = (a1 is None and a2 is None) or (a1 is not None and a2 is not None and abs(a1 - a2) < 1.0)
    route_agree = round1.get("route") == round2.get("route")
    label_agree = round1.get("derived", {}).get("sufficiency") == round2.get("derived", {}).get("sufficiency")
    question_agree = round1.get("question_clarity") == round2.get("question_clarity")
    evidence_agree = round1.get("evidence_judgement") == round2.get("evidence_judgement")

    if numeric_agree and route_agree:
        status = ("SOLO_CONFIRMED" if label_agree and question_agree and evidence_agree
                  else "SOLO_MINOR_DISAGREEMENT")
    else:
        status = "NEEDS_EXTERNAL_REVIEW"

    return {
        "case_id": round1.get("case_id"),
        "round1_created": round1.get("created_at"),
        "round2_created": round2.get("created_at"),
        "question_agreement": question_agree,
        "evidence_agreement": evidence_agree,
        "numeric_agreement": numeric_agree,
        "route_agreement": route_agree,
        "label_agreement": label_agree,
        "answer1": round1.get("human_answer"),
        "answer2": round2.get("human_answer"),
        "status": status,
    }


def recheck_case(
    path: Path, case_id: str, reviewer_id: str = "ELIAN_PRIMARY"
) -> dict[str, Any] | None:
    """Compare the two most recent rounds of a case (delayed re-check)."""
    recs = [r for r in load_annotations(path)
            if r.get("case_id") == case_id and r.get("reviewer_id") == reviewer_id]
    if len(recs) < 2:
        return None
    return compare_rounds(recs[-2], recs[-1])
