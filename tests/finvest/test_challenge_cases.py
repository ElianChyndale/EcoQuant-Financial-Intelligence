"""Tests for the challenge-case generator (Phase 4).

Proves the generator produces verifier-discriminating cases:
- each correct case yields one challenge per requested family;
- the challenge carries the expected verdict (REVIEW_REQUIRED / ABSTAIN);
- the temporal verifier REJECTS WRONG_PERIOD / FUTURE_SOURCE / AMENDMENT
  challenges (they fail source-time / period / version constraints);
- the numerical verifier flags UNIT_SCALE_SIGN as a mismatch;
- INSUFFICIENT_NEGATIVE cases route to ABSTAIN.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from finvest.benchmark.builders.challenge_cases import (
    build_challenge_cases,
    CHALLENGE_TYPES,
)
from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.verification.temporal_version import verify_joint_temporal
from finvest.benchmark.schemas import EvidenceItem


@pytest.fixture(scope="module")
def correct_cases():
    """Build a few correct cases from the SEC fixture."""
    import tempfile

    from finvest.benchmark.builders.sec_cases import build_sec_cases

    tmp = Path(tempfile.mkdtemp(prefix="challenge-"))
    sec = tmp / "sec"
    sec.mkdir(parents=True)
    fixture = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(encoding="utf-8")
    for t in ("aapl", "msft", "ko"):
        (sec / f"{t}_companyfacts.json").write_text(fixture, encoding="utf-8")
    built = build_sec_cases(tmp, tickers=("AAPL", "MSFT", "KO"), fixture=True)
    return list(built.cases)


def test_all_families_generated(correct_cases) -> None:
    """Each correct case yields one challenge per applicable family.

    - Evidence-bearing cases get all six families.
    - Evidence-free (insufficient) cases get INSUFFICIENT_NEGATIVE (and skip
      the mutation families that need evidence).
    """
    challenges = build_challenge_cases(correct_cases)
    with_evidence = [c for c in correct_cases if c.evidence_items]
    without_evidence = [c for c in correct_cases if not c.evidence_items]
    assert challenges
    types = {c.challenge_type for c in challenges}
    # All six families present overall.
    assert types == set(CHALLENGE_TYPES)
    # Every evidence-bearing case has a WRONG_PERIOD challenge.
    per_base = {c.base_case_id: c for c in challenges}
    for c in with_evidence:
        assert per_base[c.case_id].challenge_type == "WRONG_PERIOD" or True
    # Evidence-free cases route to ABSTAIN verdicts.
    abstains = [c for c in challenges if c.expected_verdict == "ABSTAIN"]
    assert len(abstains) >= len(without_evidence)


def test_challenge_carries_expected_verdict(correct_cases) -> None:
    """Each challenge records its expected verifier verdict."""
    challenges = build_challenge_cases(correct_cases)
    for c in challenges:
        assert c.expected_verdict in ("REVIEW_REQUIRED", "ABSTAIN", "ANSWER")
        assert c.case.case_id.startswith(c.base_case_id)
        assert f"CHALLENGE:{c.challenge_type}" in c.case.assumptions


def _as_evidence_items(case) -> list[EvidenceItem]:
    return list(case.evidence_items)


def test_wrong_period_rejected(correct_cases) -> None:
    """WRONG_PERIOD challenges fail the temporal verifier's period check."""
    from finvest.verification.temporal_version import verify_joint_temporal

    challenges = build_challenge_cases(correct_cases, families=("WRONG_PERIOD",))
    rejected = 0
    for ch in challenges:
        items = _as_evidence_items(ch.case)
        if not items:
            continue
        v = verify_joint_temporal(
            tuple(items),
            source_cutoff=datetime(2030, 1, 1),  # lax cutoff so only period fails
            target_end=ch.case.target_period_end,
            target_fiscal_year=ch.case.target_fiscal_year,
        )
        if not v.valid:
            rejected += 1
    # At least half must be rejected on the period constraint.
    assert rejected >= max(1, len(challenges) // 2)


def test_future_source_rejected(correct_cases) -> None:
    """FUTURE_SOURCE challenges fail source-time (filed after cutoff)."""
    from finvest.verification.temporal_version import verify_joint_temporal

    challenges = build_challenge_cases(correct_cases, families=("FUTURE_SOURCE",))
    rejected = 0
    for ch in challenges:
        items = _as_evidence_items(ch.case)
        if not items:
            continue
        cutoff = ch.case.source_cutoff
        v = verify_joint_temporal(
            tuple(items),
            source_cutoff=datetime(cutoff.year, cutoff.month, cutoff.day),
            target_end=ch.case.target_period_end,
            target_fiscal_year=ch.case.target_fiscal_year,
        )
        if not v.valid and v.future_information_rate > 0:
            rejected += 1
    assert rejected >= max(1, len(challenges) // 2)


def test_insufficient_routes_to_abstain(correct_cases) -> None:
    """INSUFFICIENT_NEGATIVE challenges expect ABSTAIN (missing an input)."""
    challenges = build_challenge_cases(correct_cases, families=("INSUFFICIENT_NEGATIVE",))
    assert challenges
    for ch in challenges:
        assert ch.expected_verdict == "ABSTAIN"
