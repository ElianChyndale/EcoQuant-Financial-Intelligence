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


# --- Hand-designed challenges (P1-1: independent of the mutation generator) ---
# These are NOT produced by _CHALLENGE_BUILDERS; they encode real-world failure
# patterns (restatement conflict, cross-period scope, unit-swap) by hand so the
# verifier is not only tested against its own mutation rules (same-rule-generates
# + same-rule-detects would overestimate robustness).


def hand_designed_challenges() -> list[ChallengeCase]:
    """Hand-built challenge cases with explicit evidence (no generator loop)."""
    from datetime import date as _date

    from finvest.benchmark.schemas import CalculationProgram, EvidenceItem, RequirementGraph

    def _item(eid: str, concept: str, val: str, end: str, filed: str, form: str = "10-K") -> EvidenceItem:
        return EvidenceItem(
            evidence_id=eid, document_id=f"HD-{eid}",
            document_version=form, filing_date=_date.fromisoformat(filed),
            valid_from=_date.fromisoformat("2022-10-01"), valid_to=_date.fromisoformat(end),
            text_span=f"{concept} {val} USD 2022-10-01 {end} {filed} {form}",
            concept=concept, unit="USD", content_hash=eid,
        )

    # 1. RESTATEMENT_CONFLICT: two filings for the SAME concept/period with
    #    DIFFERENT values; a naive verifier accepts whichever is retrieved.
    restatement = FinVestCase(
        case_id="HD-restatement-conflict",
        base_question_id="hd-bq-restatement",
        issuer_id="AAPL", jurisdiction="US",
        question="What is AAPL net income for FY2023 (restated)?",
        source_cutoff=datetime(2024, 2, 1),
        target_period_start=_date(2022, 10, 1),
        target_period_end=_date(2023, 9, 30), target_fiscal_year="FY2023",
        answer_type="extractive",
        gold_answer={"value": 97000000000.0, "unit": "USD"},
        decision_label="REVIEW", sufficiency_label="CONFLICTING",
        requirement_graph=None,
        acceptable_evidence_sets=(), minimal_evidence_sets=(),
        evidence_items=(
            _item("HD-AAPL-NetIncomeLoss-1", "NetIncomeLoss", "96995000000", "2023-09-30", "2023-11-03"),
            _item("HD-AAPL-NetIncomeLoss-2", "NetIncomeLoss", "97009000000", "2023-09-30", "2024-01-25"),
        ),
        version_relations=(),
        known_conflicts=("two filings differ for same period",),
    )
    # 2. CROSS_PERIOD_SCOPE: a 10-Q (quarterly) value presented as the full-year
    #    answer — period scope mismatch a generator would not encode.
    cross_period = FinVestCase(
        case_id="HD-cross-period-scope",
        base_question_id="hd-bq-cross-period",
        issuer_id="MSFT", jurisdiction="US",
        question="What is MSFT total revenue for FY2023?",
        source_cutoff=datetime(2023, 8, 1),
        target_period_start=_date(2022, 7, 1),
        target_period_end=_date(2023, 6, 30), target_fiscal_year="FY2023",
        answer_type="extractive",
        gold_answer={"value": 100000000000.0, "unit": "USD"},
        decision_label="REVIEW", sufficiency_label="PARTIAL",
        requirement_graph=None,
        acceptable_evidence_sets=(), minimal_evidence_sets=(),
        evidence_items=(
            _item("HD-MSFT-Revenues-Q4", "Revenues", "62000000000", "2023-06-30", "2023-07-25", form="10-Q"),
        ),
        version_relations=(),
    )
    # 3. UNIT_SWAP: value correct for a different unit scale (EUR vs USD).
    unit_swap = FinVestCase(
        case_id="HD-unit-swap",
        base_question_id="hd-bq-unit",
        issuer_id="KO", jurisdiction="US",
        question="What is KO revenue for FY2023 in USD?",
        source_cutoff=datetime(2024, 2, 1),
        target_period_start=_date(2023, 1, 1),
        target_period_end=_date(2023, 12, 31), target_fiscal_year="FY2023",
        answer_type="extractive",
        gold_answer={"value": 45000000000.0, "unit": "USD"},
        decision_label="REVIEW", sufficiency_label="REFUTED",
        requirement_graph=None,
        acceptable_evidence_sets=(), minimal_evidence_sets=(),
        evidence_items=(
            EvidenceItem(
                evidence_id="HD-KO-Revenues-EUR", document_id="HD-KO-Revenues-EUR",
                document_version="10-K", filing_date=_date(2024, 2, 1),
                valid_from=_date(2023, 1, 1), valid_to=_date(2023, 12, 31),
                text_span="Revenues 41000000000 EUR 2023-01-01 2023-12-31 2024-02-01 10-K",
                concept="Revenues", unit="EUR", content_hash="HD-KO-Revenues-EUR",
            ),
        ),
        version_relations=(),
    )
    return [
        ChallengeCase("HD-restatement-conflict", "hd-bq-restatement", "HAND_DESIGNED_RESTATEMENT_CONFLICT", restatement, "REVIEW_REQUIRED"),
        ChallengeCase("HD-cross-period-scope", "hd-bq-cross-period", "HAND_DESIGNED_CROSS_PERIOD", cross_period, "REVIEW_REQUIRED"),
        ChallengeCase("HD-unit-swap", "hd-bq-unit", "HAND_DESIGNED_UNIT_SWAP", unit_swap, "REVIEW_REQUIRED"),
    ]


def challenge_report(
    correct_cases: list[FinVestCase],
    *,
    verifier_fn: Any = None,
) -> dict[str, Any]:
    """Robustness report: mutation detection rate + clean-case false-rejection.

    If ``verifier_fn`` is given (callable case -> bool "valid"), we compute:
      - mutation_detection_rate: share of mutations the verifier REJECTS;
      - clean_case_false_rejection_rate: share of CORRECT cases the verifier
        wrongly rejects.
    Without a verifier, the report still enumerates hand-designed + generated
    challenges with their expected verdicts (13/13 killed is NOT generalizable).
    """
    from finvest.verification.temporal_version import verify_joint_temporal

    generated = build_challenge_cases(correct_cases)
    hand = hand_designed_challenges()

    def _verdict_valid(case: FinVestCase) -> bool:
        items = tuple(case.evidence_items)
        if not items:
            return False
        v = verify_joint_temporal(
            items,
            source_cutoff=case.source_cutoff or datetime(2030, 1, 1),
            target_end=case.target_period_end,
            target_fiscal_year=case.target_fiscal_year,
            version_relations=case.version_relations,
        )
        return v.valid

    def _rejects(ch: ChallengeCase) -> bool:
        if verifier_fn is not None:
            return not bool(verifier_fn(ch.case))
        return not _verdict_valid(ch.case)

    mutations = generated + hand
    rejected = sum(1 for ch in mutations if _rejects(ch))
    clean_rejected = sum(1 for c in correct_cases if not _verdict_valid(c))

    return {
        "generated_challenges": len(generated),
        "hand_designed_challenges": len(hand),
        "total_challenges": len(mutations),
        "mutation_detection_rate": round(rejected / max(len(mutations), 1), 4),
        "clean_cases": len(correct_cases),
        "clean_case_false_rejection_rate": round(clean_rejected / max(len(correct_cases), 1), 4),
        "note": (
            "mutation_detection_rate measures REJECTION of both generator "
            "mutants AND hand-designed independent cases; 13/13 killed on "
            "known mutants alone does NOT imply real-world verifier recall. "
            "clean_case_false_rejection_rate measures over-conservatism."
        ),
        "hand_designed_types": [ch.challenge_type for ch in hand],
    }
