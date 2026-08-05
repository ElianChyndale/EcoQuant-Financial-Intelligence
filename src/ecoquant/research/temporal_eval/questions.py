"""Temporal question construction for E3: three required real question classes.

Questions are derived from the real SEC facts, covering the three required
categories from the programme blueprint:

- ``old_vs_new``: the same metric differs between an old and a newer report
  (adjacent years) — tests whether the system uses the latest valid value.
- ``amended_vs_original``: a 10-K/A restates a 10-K value for the same period —
  tests contradiction detection.
- ``cross_period``: a metric is reported both annually (10-K) and quarterly
  (10-Q) — tests period-aware retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import groupby

from .sec_adapter import SecBundle, SecFact


@dataclass(frozen=True)
class TemporalQuestion:
    question_id: str
    question: str
    ticker: str
    concept: str
    valid_at: date
    source_cutoff: date
    gold_answer: float
    gold_evidence_ids: frozenset[str]
    is_contradiction: bool
    question_class: str  # old_vs_new | amended_vs_original | cross_period


def build_temporal_questions(bundle: SecBundle) -> tuple[TemporalQuestion, ...]:
    """Construct the three temporal question classes from real SEC facts."""
    questions: list[TemporalQuestion] = []
    questions.extend(_old_vs_new_questions(bundle))
    questions.extend(_amended_vs_original_questions(bundle))
    questions.extend(_cross_period_questions(bundle))
    return tuple(questions)


def _facts_by_concept(bundle: SecBundle, ticker: str) -> dict[str, list[SecFact]]:
    by_concept: dict[str, list[SecFact]] = {}
    for fact in bundle.facts:
        if fact.ticker == ticker:
            by_concept.setdefault(fact.concept, []).append(fact)
    return by_concept


def _old_vs_new_questions(bundle: SecBundle) -> list[TemporalQuestion]:
    """Same concept reported in two adjacent years with different 10-K values."""
    questions: list[TemporalQuestion] = []
    for ticker in bundle.companies:
        by_concept = _facts_by_concept(bundle, ticker)
        for concept, facts in by_concept.items():
            annual = {
                fact.end.year: (fact.end, fact.val, fact.fact_id)
                for fact in facts
                if fact.form == "10-K" and fact.end.month == 12
            }
            years = sorted(annual)
            for older, newer in zip(years, years[1:]):
                if newer != older + 1:
                    continue
                old_end, old_val, old_id = annual[older]
                new_end, new_val, new_id = annual[newer]
                if abs(old_val - new_val) < 1e-6:
                    continue  # no real change → not a useful temporal question
                valid_at = new_end
                source_cutoff = date(new_end.year, 12, 31)
                questions.append(TemporalQuestion(
                    question_id=f"e3-{ticker}-oldnew-{concept}-{newer}",
                    question=f"What was {concept} for {ticker} in fiscal year {newer}?",
                    ticker=ticker, concept=concept,
                    valid_at=valid_at, source_cutoff=source_cutoff,
                    gold_answer=new_val,
                    gold_evidence_ids=frozenset({new_id}),
                    is_contradiction=False,
                    question_class="old_vs_new",
                ))
    return questions


def _amended_vs_original_questions(bundle: SecBundle) -> list[TemporalQuestion]:
    """Same (concept, end) with a 10-K and a 10-K/A of different value."""
    questions: list[TemporalQuestion] = []
    for ticker in bundle.companies:
        by_concept = _facts_by_concept(bundle, ticker)
        for concept, facts in by_concept.items():
            # Group by (end, form) where form is 10-K or 10-K/A.
            by_end: dict[date, dict[str, SecFact]] = {}
            for fact in facts:
                if fact.form in {"10-K", "10-K/A"}:
                    by_end.setdefault(fact.end, {})[fact.form] = fact
            for end, forms in sorted(by_end.items()):
                original = forms.get("10-K")
                amended = forms.get("10-K/A")
                if original is None or amended is None:
                    continue
                if abs(original.val - amended.val) < 1e-6:
                    continue  # amendment with no value change isn't a contradiction
                source_cutoff = amended.filed
                questions.append(TemporalQuestion(
                    question_id=f"e3-{ticker}-amended-{concept}-{end}",
                    question=f"What is the latest restated value of {concept} for {ticker} for the period ending {end}?",
                    ticker=ticker, concept=concept,
                    valid_at=end, source_cutoff=source_cutoff,
                    gold_answer=amended.val,
                    gold_evidence_ids=frozenset({amended.fact_id}),
                    is_contradiction=True,
                    question_class="amended_vs_original",
                ))
    return questions


def _cross_period_questions(bundle: SecBundle) -> list[TemporalQuestion]:
    """Same concept reported in both 10-K and 10-Q for the same period end."""
    questions: list[TemporalQuestion] = []
    for ticker in bundle.companies:
        by_concept = _facts_by_concept(bundle, ticker)
        for concept, facts in by_concept.items():
            by_end_form: dict[tuple[date, str], SecFact] = {}
            for fact in facts:
                if fact.form in {"10-K", "10-Q"}:
                    by_end_form.setdefault((fact.end, fact.form), fact)
            for (end, form), fact in sorted(by_end_form.items()):
                other_form = "10-K" if form == "10-Q" else "10-Q"
                other = by_end_form.get((end, other_form))
                if other is None or abs(other.val - fact.val) < 1e-6:
                    continue
                # The 10-K annual value is the gold; the 10-Q is the quarterly alternative.
                annual = fact if form == "10-K" else other
                questions.append(TemporalQuestion(
                    question_id=f"e3-{ticker}-cross-{concept}-{end}",
                    question=f"What is the annual value of {concept} for {ticker} for the period ending {end}?",
                    ticker=ticker, concept=concept,
                    valid_at=end, source_cutoff=date(end.year, 12, 31),
                    gold_answer=annual.val,
                    gold_evidence_ids=frozenset({annual.fact_id}),
                    is_contradiction=False,
                    question_class="cross_period",
                ))
    return questions
