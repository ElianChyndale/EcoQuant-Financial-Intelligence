"""FinVEST challenge-case generator (Phase 4).

Generates high-value challenge cases from CORRECT cases by applying one
verifier-relevant perturbation per case. These make the verifier and the
abstention route show measurable discrimination, instead of the near-perfect
pass rates that correct-only cases produce.

Challenge families (one perturbation each):
  WRONG_PERIOD          — evidence valid_from/valid_to moved to a different FY
  FUTURE_SOURCE         — evidence filed AFTER the source cutoff
  AMENDMENT_MISMATCH    — evidence marked as latest but superseded by an amendment
  UNIT_SCALE_SIGN       — value scale (x1000 / USD-vs-millions) or sign flipped
  DUPLICATE_AMBIGUOUS   — two facts with the same identity but different values
  INSUFFICIENT_NEGATIVE — evidence set missing a required input (honest ABSTAIN)

Each challenge carries the correct case's gold so the verifier can be scored on
"rejects the mutated case" (the expected outcome is REVIEW_REQUIRED / not valid).

These are MACHINE-generated candidate challenges, NOT human-validated gold.
Human annotators must review before they count as benchmark gold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from finvest.benchmark.schemas import (
    CalculationProgram,
    EvidenceItem,
    FinVestCase,
    VersionRelation,
)


@dataclass(frozen=True)
class ChallengeCase:
    """One challenge: a mutated case + the expected verifier outcome."""

    case_id: str
    base_case_id: str
    challenge_type: str  # one of the CHALLENGE_TYPES
    case: FinVestCase
    expected_verdict: str  # REVIEW_REQUIRED (mutated must fail) | ABSTAIN | ANSWER

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "base_case_id": self.base_case_id,
            "challenge_type": self.challenge_type,
            "expected_verdict": self.expected_verdict,
            "question": self.case.question,
        }


CHALLENGE_TYPES = (
    "WRONG_PERIOD", "FUTURE_SOURCE", "AMENDMENT_MISMATCH",
    "UNIT_SCALE_SIGN", "DUPLICATE_AMBIGUOUS", "INSUFFICIENT_NEGATIVE",
)


def _shift_date(d: date | None, years: int) -> date | None:
    if d is None:
        return None
    try:
        return date(d.year + years, d.month, d.day)
    except ValueError:  # e.g. Feb 29
        return date(d.year + years, d.month, min(d.day, 28))


def _mutate_evidence(item: EvidenceItem, **overrides: Any) -> EvidenceItem:
    """Rebuild an EvidenceItem with overrides (dataclasses.replace)."""
    import dataclasses

    return dataclasses.replace(item, **overrides)


def _wrong_period(base: FinVestCase) -> ChallengeCase:
    """Move evidence valid period to a different fiscal year."""
    items = tuple(
        _mutate_evidence(
            it, valid_from=_shift_date(it.valid_from, -1), valid_to=_shift_date(it.valid_to, -1),
        )
        for it in base.evidence_items
    )
    mutated = _rebuild_case(base, "wrong-period", items, challenge_type="WRONG_PERIOD")
    return ChallengeCase(mutated.case_id, base.case_id, "WRONG_PERIOD", mutated, "REVIEW_REQUIRED")


def _future_source(base: FinVestCase) -> ChallengeCase:
    """Move evidence filing date after the source cutoff (future information)."""
    cutoff = base.source_cutoff
    items = tuple(
        _mutate_evidence(
            it, filing_date=date(cutoff.year + 1, cutoff.month, cutoff.day),
        )
        for it in base.evidence_items
    )
    mutated = _rebuild_case(base, "future-source", items, challenge_type="FUTURE_SOURCE")
    return ChallengeCase(mutated.case_id, base.case_id, "FUTURE_SOURCE", mutated, "REVIEW_REQUIRED")


def _amendment_mismatch(base: FinVestCase) -> ChallengeCase:
    """Mark evidence as latest but add a superseding version relation."""
    items = base.evidence_items
    if not items:
        return _abstain_challenge(base, "AMENDMENT_MISMATCH", "amendment-mismatch")
    # A later "amended" doc supersedes the first evidence doc.
    later = _mutate_evidence(
        items[0],
        document_version="10-K/A",
        filing_date=_shift_date(items[0].filing_date, 1) or items[0].filing_date,
        evidence_id=items[0].evidence_id + ":amended",
    )
    mutated = _rebuild_case(
        base, "amendment-mismatch", items + (later,),
        version_relations=(
            VersionRelation(items[0].document_id, later.document_id, "SUPERSEDES"),
        ),
        challenge_type="AMENDMENT_MISMATCH",
    )
    return ChallengeCase(mutated.case_id, base.case_id, "AMENDMENT_MISMATCH", mutated, "REVIEW_REQUIRED")


def _unit_scale_sign(base: FinVestCase) -> ChallengeCase:
    """Flip scale (x1000) and sign on the evidence values.

    EvidenceItem has no ``value`` field (values live in text_span); we rewrite
    the text_span by scaling and negating every numeric token, and set scale.
    """
    import re as _re

    def _scale_text(span: str | None) -> str | None:
        if not span:
            return span
        return _re.sub(
            r"-?\d+(?:\.\d+)?",
            lambda m: f"{-(float(m.group(0)) * 1000):.0f}",
            span,
        )

    items = tuple(
        _mutate_evidence(it, text_span=_scale_text(it.text_span), scale="1000")
        for it in base.evidence_items
    )
    mutated = _rebuild_case(base, "unit-scale-sign", items, challenge_type="UNIT_SCALE_SIGN")
    return ChallengeCase(mutated.case_id, base.case_id, "UNIT_SCALE_SIGN", mutated, "REVIEW_REQUIRED")


def _duplicate_ambiguous(base: FinVestCase) -> ChallengeCase:
    """Add a second fact with the same identity but a different value."""
    items = base.evidence_items
    if not items:
        return _abstain_challenge(base, "DUPLICATE_AMBIGUOUS", "duplicate-ambiguous")
    dup = _mutate_evidence(
        items[0],
        evidence_id=items[0].evidence_id + ":dup",
        text_span=f"{items[0].text_span} DUP-ALT",  # ambiguous duplicate representation
    )
    mutated = _rebuild_case(
        base, "duplicate-ambiguous", items + (dup,), challenge_type="DUPLICATE_AMBIGUOUS",
    )
    return ChallengeCase(mutated.case_id, base.case_id, "DUPLICATE_AMBIGUOUS", mutated, "REVIEW_REQUIRED")


def _insufficient_negative(base: FinVestCase) -> ChallengeCase:
    """Drop one required input (honest ABSTAIN expected)."""
    items = base.evidence_items
    if len(items) < 2:
        return _abstain_challenge(base, "INSUFFICIENT_NEGATIVE", "insufficient-negative")
    reduced = items[:1]  # keep only the first input
    mutated = _rebuild_case(
        base, "insufficient-negative", reduced, challenge_type="INSUFFICIENT_NEGATIVE",
    )
    return ChallengeCase(mutated.case_id, base.case_id, "INSUFFICIENT_NEGATIVE", mutated, "ABSTAIN")


def _rebuild_abstain(base: FinVestCase, suffix: str, challenge_type: str) -> FinVestCase:
    """Minimal mutated case when the base lacks enough evidence."""
    return _rebuild_case(
        base, suffix, base.evidence_items,
        decision_label="ABSTAIN", challenge_type=challenge_type,
    )


def _abstain_challenge(base: FinVestCase, challenge_type: str, suffix: str) -> ChallengeCase:
    """A ChallengeCase whose mutated case is the abstain variant (no evidence)."""
    mutated = _rebuild_abstain(base, suffix, challenge_type)
    return ChallengeCase(mutated.case_id, base.case_id, challenge_type, mutated, "ABSTAIN")


def _rebuild_case(
    base: FinVestCase,
    suffix: str,
    items: tuple[EvidenceItem, ...],
    *,
    version_relations: tuple[VersionRelation, ...] = (),
    decision_label: str = "REVIEW",
    challenge_type: str | None = None,
) -> FinVestCase:
    """Copy a case with a challenge suffix, swapped evidence, adjusted labels."""
    import dataclasses

    tag = f"CHALLENGE:{challenge_type or suffix.upper()}"
    return dataclasses.replace(
        base,
        case_id=f"{base.case_id}-{suffix}",
        evidence_items=items,
        decision_label=decision_label,
        sufficiency_label="REFUTED" if decision_label == "REVIEW" else "INSUFFICIENT",
        version_relations=version_relations or base.version_relations,
        # Keep gold but mark the case as a challenge (gold is for scoring the
        # verifier's rejection, not for retrieval).
        assumptions=base.assumptions + (tag,),
        acceptable_evidence_sets=(),
        minimal_evidence_sets=(),
    )


_CHALLENGE_BUILDERS = {
    "WRONG_PERIOD": _wrong_period,
    "FUTURE_SOURCE": _future_source,
    "AMENDMENT_MISMATCH": _amendment_mismatch,
    "UNIT_SCALE_SIGN": _unit_scale_sign,
    "DUPLICATE_AMBIGUOUS": _duplicate_ambiguous,
    "INSUFFICIENT_NEGATIVE": _insufficient_negative,
}


def build_challenge_cases(
    correct_cases: list[FinVestCase],
    *,
    families: tuple[str, ...] = CHALLENGE_TYPES,
) -> list[ChallengeCase]:
    """Generate challenge cases from a list of correct cases.

    For each correct case and each requested family, build one challenge.
    Only cases with enough evidence are used per family (insufficient bases
    are skipped for families that need >=2 evidence items).
    """
    challenges: list[ChallengeCase] = []
    for base in correct_cases:
        for family in families:
            if not base.evidence_items and family != "INSUFFICIENT_NEGATIVE":
                continue
            if len(base.evidence_items) < 2 and family == "AMENDMENT_MISMATCH":
                continue
            builder = _CHALLENGE_BUILDERS[family]
            challenges.append(builder(base))
    return challenges
