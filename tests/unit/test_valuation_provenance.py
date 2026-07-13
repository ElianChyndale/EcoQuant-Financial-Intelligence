"""Task 7A evidence-to-valuation provenance contract tests."""

from __future__ import annotations

from datetime import date

import pytest

from ecoquant.uncertainty.decision import DecisionCode
from ecoquant.valuation.bond_pricing import BondTerms
from ecoquant.valuation.policy import PolicyInput, PolicyResult, apply_policy
from ecoquant.valuation.sensitivity import compute_sensitivity


def _terms() -> BondTerms:
    return BondTerms(
        face_value=1_000.0,
        coupon_rate=0.06,
        payment_frequency=2,
        issue_date=date(2024, 1, 31),
        settlement_date=date(2025, 4, 30),
        maturity_date=date(2027, 1, 31),
    )


def _policy(
    *,
    decision_code: DecisionCode = DecisionCode.AUTO_REPORT,
    adjustments: dict[str, int] | None = None,
) -> PolicyResult:
    return PolicyResult(
        adjusted_spread_bps=150,
        recommended_haircut_bps=100,
        decision_code=decision_code,
        adjustments={"credit_spread": 50} if adjustments is None else adjustments,
    )


def _compute(
    policy: PolicyResult | None = None,
    risk_channel_map: dict[str, str] | None = None,
    **overrides: object,
):
    kwargs: dict[str, object] = {
        "issuer": "GreenCorp",
        "asset_id": "XS1234567890",
        "evidence_id": "evidence-abc-123",
        "rule_id": "spread-credit",
        "rule_version": "1.0",
        "valid_time": "2025-04-30T00:00:00Z",
        "source_time": "2025-04-29T12:00:00Z",
    }
    kwargs.update(overrides)
    return compute_sensitivity(
        _terms(),
        0.05,
        100,
        policy or _policy(),
        {"credit_spread": "credit"} if risk_channel_map is None else risk_channel_map,
        **kwargs,  # type: ignore[arg-type]
    )


def test_supported_scenario_preserves_complete_provenance() -> None:
    result = _compute()
    scenario = result.scenarios[0]

    assert scenario.evidence_id == "evidence-abc-123"
    assert scenario.issuer == "GreenCorp"
    assert scenario.asset_id == "XS1234567890"
    assert scenario.risk_factor == "credit_spread"
    assert scenario.risk_channel == "credit"
    assert scenario.rule_id == "spread-credit"
    assert scenario.rule_version == "1.0"
    assert scenario.base_spread_bps == 100
    assert scenario.spread_delta_bps == 50
    assert scenario.adjusted_spread_bps == 150
    assert scenario.valid_time == "2025-04-30T00:00:00Z"
    assert scenario.source_time == "2025-04-29T12:00:00Z"
    assert scenario.decision_code is DecisionCode.AUTO_REPORT
    assert scenario.day_count_convention == "Actual/Actual ICMA"
    assert "nominal annual yield" in scenario.compounding_convention
    assert scenario.settlement_date == date(2025, 4, 30)
    assert scenario.maturity_date == date(2027, 1, 31)
    assert scenario.coupon_frequency == 2
    assert scenario.base_dirty_price == result.base_dirty_price
    assert scenario.base_clean_price == result.base_clean_price
    assert scenario.adjusted_dirty_price < scenario.base_dirty_price
    assert scenario.adjusted_clean_price < scenario.base_clean_price
    assert scenario.accrued_interest == pytest.approx(result.base_accrued_interest)
    assert scenario.macaulay_duration > 0.0
    assert scenario.modified_duration > 0.0
    assert scenario.convexity > 0.0


def test_supported_mapping_rejects_missing_evidence_id() -> None:
    with pytest.raises(ValueError, match="evidence_id"):
        _compute(evidence_id="")


def test_unsupported_mapping_is_explicit_and_cannot_adjust_terms() -> None:
    result = _compute(
        policy=_policy(adjustments={"unknown_factor": 50}),
        risk_channel_map={},
    )
    unsupported = result.unsupported_mappings[0]

    assert result.scenarios == ()
    assert unsupported.status == "unsupported_risk_mapping"
    assert unsupported.evidence_id == "evidence-abc-123"
    assert unsupported.risk_factor == "unknown_factor"
    assert unsupported.spread_delta_bps == 0
    assert unsupported.adjusted_spread_bps == unsupported.base_spread_bps == 100
    assert unsupported.haircut_delta_bps == 0


def test_insufficient_evidence_produces_stable_no_adjustment_result() -> None:
    policy = _policy(
        decision_code=DecisionCode.INSUFFICIENT_EVIDENCE,
        adjustments={},
    )
    result = _compute(policy=policy)

    assert result.status == "insufficient_evidence"
    assert result.scenarios == ()
    assert result.unsupported_mappings == ()
    assert result.effective_spread_bps == result.base_spread_bps == 100


def test_each_spread_scenario_is_repriced_not_scaled() -> None:
    first = _compute(policy=_policy(adjustments={"credit_spread": 25})).scenarios[0]
    second = _compute(policy=_policy(adjustments={"credit_spread": 50})).scenarios[0]

    assert first.adjusted_spread_bps == 125
    assert second.adjusted_spread_bps == 150
    assert second.adjusted_dirty_price < first.adjusted_dirty_price
    assert second.modified_duration != first.modified_duration
    assert second.convexity != first.convexity


def test_policy_unsupported_factor_flows_to_visible_no_adjustment_record() -> None:
    policy = apply_policy(
        PolicyInput(
            decision_code=DecisionCode.AUTO_REPORT,
            evidence_ids=("evidence-abc-123",),
            risk_factors={"unknown_factor": 0.9},
            risk_channel_map={},
            extraction_valid=True,
            base_spread_bps=100,
        )
    )
    result = _compute(policy=policy, risk_channel_map={})

    assert result.effective_spread_bps == 100
    assert result.unsupported_mappings[0].risk_factor == "unknown_factor"
    assert result.unsupported_mappings[0].haircut_delta_bps == 0
