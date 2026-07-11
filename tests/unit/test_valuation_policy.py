"""Valuation policy safety tests for Task 7.

These tests verify that the valuation policy engine correctly gates
spread/haircut adjustments behind decision codes and extraction validity,
and that all adjustments are bounded.
"""

from __future__ import annotations

import pytest

from ecoquant.uncertainty.decision import DecisionCode
from ecoquant.valuation.policy import PolicyInput, PolicyResult, apply_policy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def base_spread() -> int:
    """Canonical base spread for testing."""
    return 145


@pytest.fixture()
def insufficient_input(base_spread: int) -> PolicyInput:
    """PolicyInput where evidence is insufficient (decision code 0)."""
    return PolicyInput(
        decision_code=DecisionCode.INSUFFICIENT_EVIDENCE,
        evidence_ids=(),
        risk_factors={"credit": 0.8, "liquidity": 0.6},
        extraction_valid=True,
        base_spread_bps=base_spread,
        max_spread_delta_bps=50,
        max_haircut_bps=500,
    )


@pytest.fixture()
def invalid_extraction_input(base_spread: int) -> PolicyInput:
    """PolicyInput where extraction failed."""
    return PolicyInput(
        decision_code=DecisionCode.AUTO_REPORT,
        evidence_ids=("ev-1", "ev-2"),
        risk_factors={"credit": 0.8},
        extraction_valid=False,
        base_spread_bps=base_spread,
        max_spread_delta_bps=50,
        max_haircut_bps=500,
    )


@pytest.fixture()
def auto_report_input(base_spread: int) -> PolicyInput:
    """PolicyInput for a fully supported AUTO_REPORT decision."""
    return PolicyInput(
        decision_code=DecisionCode.AUTO_REPORT,
        evidence_ids=("ev-1", "ev-2", "ev-3"),
        risk_factors={"credit": 0.7, "liquidity": 0.5, "market": 0.3},
        extraction_valid=True,
        base_spread_bps=base_spread,
        max_spread_delta_bps=50,
        max_haircut_bps=500,
    )


@pytest.fixture()
def human_review_input(base_spread: int) -> PolicyInput:
    """PolicyInput for a HUMAN_REVIEW_REQUIRED decision."""
    return PolicyInput(
        decision_code=DecisionCode.HUMAN_REVIEW_REQUIRED,
        evidence_ids=("ev-1",),
        risk_factors={"credit": 0.6},
        extraction_valid=True,
        base_spread_bps=base_spread,
        max_spread_delta_bps=50,
        max_haircut_bps=500,
    )


# ---------------------------------------------------------------------------
# Tests: insufficient evidence / invalid extraction cannot change spread
# ---------------------------------------------------------------------------


class TestInsufficientEvidenceBlocksAdjustment:
    """Gate 1: INSUFFICIENT_EVIDENCE or invalid extraction must not adjust spread."""

    def test_insufficient_evidence_cannot_change_spread(
        self,
        insufficient_input: PolicyInput,
        base_spread: int,
    ) -> None:
        result = apply_policy(insufficient_input)
        assert isinstance(result, PolicyResult)
        assert result.adjusted_spread_bps == base_spread

    def test_insufficient_extraction_cannot_change_spread(
        self,
        invalid_extraction_input: PolicyInput,
        base_spread: int,
    ) -> None:
        result = apply_policy(invalid_extraction_input)
        assert isinstance(result, PolicyResult)
        assert result.adjusted_spread_bps == base_spread

    def test_policy_returns_none_haircut_for_insufficient(
        self,
        insufficient_input: PolicyInput,
    ) -> None:
        result = apply_policy(insufficient_input)
        assert result.recommended_haircut_bps is None

    def test_policy_returns_none_haircut_for_invalid_extraction(
        self,
        invalid_extraction_input: PolicyInput,
    ) -> None:
        result = apply_policy(invalid_extraction_input)
        assert result.recommended_haircut_bps is None

    def test_insufficient_has_empty_adjustments(
        self,
        insufficient_input: PolicyInput,
    ) -> None:
        result = apply_policy(insufficient_input)
        assert result.adjustments == {}

    def test_invalid_extraction_has_empty_adjustments(
        self,
        invalid_extraction_input: PolicyInput,
    ) -> None:
        result = apply_policy(invalid_extraction_input)
        assert result.adjustments == {}


# ---------------------------------------------------------------------------
# Tests: supported evidence adjusts spread within bounds
# ---------------------------------------------------------------------------


class TestSupportedEvidenceAdjustsSpread:
    """Gate 3: AUTO_REPORT produces bounded spread adjustments and a haircut."""

    def test_supported_evidence_adjusts_spread(
        self,
        auto_report_input: PolicyInput,
        base_spread: int,
    ) -> None:
        result = apply_policy(auto_report_input)
        assert isinstance(result, PolicyResult)
        # Spread should move upward (risk factors are positive).
        assert result.adjusted_spread_bps >= base_spread
        # But never exceed base + max_spread_delta_bps.
        assert (
            result.adjusted_spread_bps
            <= base_spread + auto_report_input.max_spread_delta_bps
        )

    def test_policy_returns_haircut_for_sufficient(
        self,
        auto_report_input: PolicyInput,
    ) -> None:
        result = apply_policy(auto_report_input)
        assert result.recommended_haircut_bps is not None
        assert isinstance(result.recommended_haircut_bps, int)
        assert result.recommended_haircut_bps >= 0

    def test_haircut_bounded_by_max(
        self,
        auto_report_input: PolicyInput,
    ) -> None:
        result = apply_policy(auto_report_input)
        assert result.recommended_haircut_bps is not None
        assert result.recommended_haircut_bps <= auto_report_input.max_haircut_bps


# ---------------------------------------------------------------------------
# Tests: adjustment bounding
# ---------------------------------------------------------------------------


class TestAdjustmentBounding:
    """All adjustments must respect the max_spread_delta_bps cap."""

    def test_adjustment_bounded(
        self,
        auto_report_input: PolicyInput,
        base_spread: int,
    ) -> None:
        result = apply_policy(auto_report_input)
        delta = result.adjusted_spread_bps - base_spread
        assert 0 <= delta <= auto_report_input.max_spread_delta_bps

    def test_per_channel_adjustments_bounded(
        self,
        auto_report_input: PolicyInput,
    ) -> None:
        result = apply_policy(auto_report_input)
        for channel, adj in result.adjustments.items():
            assert 0 <= adj <= auto_report_input.max_spread_delta_bps, (
                f"Channel {channel!r} adjustment {adj} exceeds "
                f"max_spread_delta_bps={auto_report_input.max_spread_delta_bps}"
            )

    def test_extreme_risk_factors_still_bounded(self, base_spread: int) -> None:
        """Even with all risk factors at 1.0, the delta is clamped."""
        inp = PolicyInput(
            decision_code=DecisionCode.AUTO_REPORT,
            evidence_ids=("ev-1",),
            risk_factors={"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0},
            extraction_valid=True,
            base_spread_bps=base_spread,
            max_spread_delta_bps=50,
            max_haircut_bps=500,
        )
        result = apply_policy(inp)
        delta = result.adjusted_spread_bps - base_spread
        assert delta <= inp.max_spread_delta_bps

    def test_human_review_adjustment_bounded(
        self,
        human_review_input: PolicyInput,
        base_spread: int,
    ) -> None:
        result = apply_policy(human_review_input)
        delta = result.adjusted_spread_bps - base_spread
        assert 0 <= delta <= human_review_input.max_spread_delta_bps


# ---------------------------------------------------------------------------
# Tests: decision code preservation
# ---------------------------------------------------------------------------


class TestDecisionCodePreserved:
    """The PolicyResult must carry the governing DecisionCode."""

    def test_decision_code_preserved_insufficient(
        self,
        insufficient_input: PolicyInput,
    ) -> None:
        result = apply_policy(insufficient_input)
        assert result.decision_code is DecisionCode.INSUFFICIENT_EVIDENCE

    def test_decision_code_preserved_invalid_extraction(
        self,
        invalid_extraction_input: PolicyInput,
    ) -> None:
        result = apply_policy(invalid_extraction_input)
        # Even though input was AUTO_REPORT, extraction_valid=False
        # forces INSUFFICIENT_EVIDENCE.
        assert result.decision_code is DecisionCode.INSUFFICIENT_EVIDENCE

    def test_decision_code_preserved_auto_report(
        self,
        auto_report_input: PolicyInput,
    ) -> None:
        result = apply_policy(auto_report_input)
        assert result.decision_code is DecisionCode.AUTO_REPORT

    def test_decision_code_preserved_human_review(
        self,
        human_review_input: PolicyInput,
    ) -> None:
        result = apply_policy(human_review_input)
        assert result.decision_code is DecisionCode.HUMAN_REVIEW_REQUIRED
