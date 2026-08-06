"""Solo provisional annotation protocol (solo-v1, Phase 13).

Low-cost single-researcher provisional annotation that keeps every judgement
traceable, re-checkable, and independently overridable by a future annotator.

Status lifecycle:
    CANDIDATE_UNREVIEWED -> BLOCKED_EVIDENCE_INCOMPLETE
                         -> SOLO_PROVISIONAL (after first blind pass)
                         -> SOLO_CONFIRMED / SOLO_DISAGREEMENT (after delayed
                            self re-check)
                         -> NEEDS_EXTERNAL_REVIEW (disagreement or risk)
                         -> DOUBLE_ANNOTATED -> ADJUDICATED
                         -> HUMAN_VALIDATED_GOLD

Solo annotations are PROVISIONAL research labels, never gold.
"""

from __future__ import annotations

PROTOCOL_VERSION = "solo-v1"

# --- Question clarity (Q1) ---
Q1_CLEAR = "CLEAR"
Q1_AMBIGUOUS = "AMBIGUOUS"
Q1_INVALID = "INVALID"

# --- Evidence judgement (Q2) ---
EVIDENCE_ENOUGH = "ENOUGH"
EVIDENCE_PARTLY = "PARTLY_ENOUGH"
EVIDENCE_CONFLICTING = "CONFLICTING"
EVIDENCE_NOT_ENOUGH = "NOT_ENOUGH"

# Q2 -> system sufficiency mapping.
SUFFICIENCY_MAP = {
    EVIDENCE_ENOUGH: "SUPPORTED",
    EVIDENCE_PARTLY: "PARTIAL",
    EVIDENCE_CONFLICTING: "CONFLICTING",
    EVIDENCE_NOT_ENOUGH: "INSUFFICIENT",
}

# --- Issue flags (Q4 checkboxes) ---
ISSUE_FLAGS = (
    "WRONG_PERIOD",
    "FUTURE_SOURCE",
    "VERSION_AMENDMENT_UNCLEAR",
    "METRIC_DEFINITION_UNCLEAR",
    "UNIT_SCALE_UNCLEAR",
    "WRONG_ENTITY",
    "CALCULATION_MISMATCH",
    "MISSING_EVIDENCE",
    "NO_ISSUE",
)

# --- Route (Q5) ---
ROUTE_ANSWER = "ANSWER"
ROUTE_REVIEW = "REVIEW"
ROUTE_ABSTAIN = "ABSTAIN"

# --- Confidence (3-level) ---
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

# Legacy 1-5 -> 3-level mapping.
CONFIDENCE_LEGACY_MAP = {5: CONFIDENCE_HIGH, 4: CONFIDENCE_HIGH,
                         3: CONFIDENCE_MEDIUM, 2: CONFIDENCE_LOW,
                         1: CONFIDENCE_LOW}

# --- Annotation status ---
STATUS_CANDIDATE = "CANDIDATE_UNREVIEWED"
STATUS_BLOCKED = "BLOCKED_EVIDENCE_INCOMPLETE"
STATUS_SOLO_PROVISIONAL = "SOLO_PROVISIONAL"
STATUS_SOLO_CONFIRMED = "SOLO_CONFIRMED"
STATUS_SOLO_DISAGREEMENT = "SOLO_DISAGREEMENT"
STATUS_NEEDS_EXTERNAL = "NEEDS_EXTERNAL_REVIEW"
STATUS_DOUBLE = "DOUBLE_ANNOTATED"
STATUS_ADJUDICATED = "ADJUDICATED"
STATUS_GOLD = "HUMAN_VALIDATED_GOLD"


def confidence_from_legacy(level: int | None) -> str | None:
    """Map legacy 1-5 confidence to the 3-level scale."""
    if level is None:
        return None
    return CONFIDENCE_LEGACY_MAP.get(int(level))


def status_for_route(route: str, confidence: str, *, issue_flags: tuple[str, ...] = ()) -> str:
    """Route + confidence + issues -> provisional status (Stage 4 risk layering).

    Green (low risk): route ANSWER, confidence HIGH/MEDIUM, no hard issues
        -> SOLO_PROVISIONAL.
    Yellow (medium risk): confidence LOW, or soft issues (FUTURE_SOURCE,
        METRIC_DEFINITION_UNCLEAR, UNIT_SCALE_UNCLEAR) without hard conflict
        -> SOLO_PROVISIONAL (deferred re-check, still provisional).
    Red (high risk): route REVIEW/ABSTAIN, or hard issues (WRONG_PERIOD,
        VERSION_AMENDMENT_UNCLEAR, CALCULATION_MISMATCH, MISSING_EVIDENCE,
        WRONG_ENTITY, CONFLICTING evidence) -> NEEDS_EXTERNAL_REVIEW.
    """
    hard_issues = {
        "WRONG_PERIOD", "VERSION_AMENDMENT_UNCLEAR", "CALCULATION_MISMATCH",
        "MISSING_EVIDENCE", "WRONG_ENTITY",
    }
    if route in (ROUTE_REVIEW, ROUTE_ABSTAIN) or (hard_issues & set(issue_flags)):
        return STATUS_NEEDS_EXTERNAL
    return STATUS_SOLO_PROVISIONAL
