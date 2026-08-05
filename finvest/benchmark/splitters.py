"""FinVEST-Bench five-level isolation splitters (PREREGISTRATION §4).

Levels:
1. issuer isolation — a company never spans train/test.
2. document-family isolation — one filing's HTML/PDF/XBRL stay together.
3. temporal isolation — test uses later periods/filings.
4. question-template isolation — paraphrases of one template stay together.
5. evidence-family isolation — duplicate representations of one fact stay
   together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .schemas import FinVESTCase


@dataclass(frozen=True)
class Split:
    train: tuple[str, ...]
    test: tuple[str, ...]

    def is_disjoint(self, *, by_issuer: bool = True) -> bool:
        return set(self.train).isdisjoint(set(self.test))


def split_by_issuer(cases: list[FinVESTCase], test_issuers: set[str]) -> Split:
    """Level 1: hold out whole issuers."""
    train = [c.case_id for c in cases if c.issuer_id not in test_issuers]
    test = [c.case_id for c in cases if c.issuer_id in test_issuers]
    return Split(tuple(train), tuple(test))


def split_chronological(
    cases: list[FinVESTCase],
    cutoff: date,
) -> Split:
    """Level 3: test uses filings after the training cutoff."""
    train = [c.case_id for c in cases if c.source_cutoff.date() <= cutoff]
    test = [c.case_id for c in cases if c.source_cutoff.date() > cutoff]
    return Split(tuple(train), tuple(test))


def split_by_document_family(
    cases: list[FinVESTCase],
    test_families: set[str],
    family_of: dict[str, str],
) -> Split:
    """Level 2: hold out whole document families (filing accession)."""
    train = [c.case_id for c in cases if family_of.get(c.case_id) not in test_families]
    test = [c.case_id for c in cases if family_of.get(c.case_id) in test_families]
    return Split(tuple(train), tuple(test))


def verify_no_cross_split_leakage(
    cases: list[FinVESTCase],
    split: Split,
    *,
    issuer_of: dict[str, str],
    family_of: dict[str, str],
) -> list[str]:
    """Return violations: any issuer or document family spanning both splits."""
    violations: list[str] = []
    train_ids, test_ids = set(split.train), set(split.test)
    for level_name, key_of in (("issuer", issuer_of), ("document_family", family_of)):
        train_keys = {key_of[c] for c in train_ids}
        test_keys = {key_of[c] for c in test_ids}
        overlap = train_keys & test_keys
        if overlap:
            violations.append(f"{level_name} spans splits: {sorted(overlap)}")
    return violations
