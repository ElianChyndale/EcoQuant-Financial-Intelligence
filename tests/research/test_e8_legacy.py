from __future__ import annotations

import pytest

from ecoquant.research.integration_eval.legacy import (
    LegacyOutput,
    legacy_honesty_score,
    legacy_spread_bps,
)


def test_legacy_spread_formula() -> None:
    assert legacy_spread_bps(60.0) == 0.0
    assert legacy_spread_bps(50.0) == 20.0  # (60-50)*2
    assert legacy_spread_bps(30.0) == 60.0  # (60-30)*2


def test_legacy_has_no_evidence() -> None:
    out = legacy_honesty_score("What is AIB credit risk?", seed=42)
    assert isinstance(out, LegacyOutput)
    assert out.citation is None
    assert out.verification == "none"


def test_legacy_is_seed_deterministic() -> None:
    a = legacy_honesty_score("What is the credit risk?", seed=1)
    b = legacy_honesty_score("What is the credit risk?", seed=1)
    assert a.score == b.score
    assert a.spread_bps == b.spread_bps


def test_legacy_never_routes_to_review() -> None:
    out = legacy_honesty_score("What is the credit risk?", seed=7)
    assert out.review_status == "auto"  # legacy system never flags for review
