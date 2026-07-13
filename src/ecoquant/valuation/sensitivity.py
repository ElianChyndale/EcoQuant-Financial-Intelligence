"""Auditable evidence-to-valuation sensitivity under the frozen ICMA contract."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from ecoquant.uncertainty.decision import DecisionCode
from ecoquant.valuation.bond_pricing import (
    BondTerms,
    price_bond,
    price_bond_with_spread_shock,
)
from ecoquant.valuation.policy import PolicyResult


@dataclass(frozen=True)
class SensitivityScenario:
    """One independently repriced, fully attributable spread scenario."""

    scenario_name: str
    evidence_id: str
    issuer: str
    asset_id: str
    risk_factor: str
    risk_channel: str
    rule_id: str
    rule_version: str
    units: str
    base_spread_bps: int
    spread_delta_bps: int
    adjusted_spread_bps: int
    decision_code: DecisionCode
    day_count_convention: str
    compounding_convention: str
    settlement_date: date
    maturity_date: date
    coupon_frequency: int
    base_clean_price: float
    base_dirty_price: float
    adjusted_clean_price: float
    adjusted_dirty_price: float
    accrued_interest: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    valid_time: str
    source_time: str
    status: str = "adjusted"

    @property
    def bond_id(self) -> str:
        return self.asset_id

    @property
    def base_price(self) -> float:
        return self.base_dirty_price

    @property
    def adjusted_duration(self) -> float:
        return self.modified_duration

    @property
    def adjusted_convexity(self) -> float:
        return self.convexity


@dataclass(frozen=True)
class UnsupportedMapping:
    """Visible no-adjustment result for an unmapped risk factor."""

    evidence_id: str
    issuer: str
    asset_id: str
    risk_factor: str
    rule_id: str
    rule_version: str
    base_spread_bps: int
    spread_delta_bps: int
    adjusted_spread_bps: int
    haircut_delta_bps: int
    decision_code: DecisionCode
    valid_time: str
    source_time: str
    status: str = "unsupported_risk_mapping"


@dataclass(frozen=True)
class ValuationSensitivityResult:
    """Base valuation plus supported and unsupported sensitivity outcomes."""

    base_clean_price: float
    base_dirty_price: float
    base_accrued_interest: float
    base_macaulay_duration: float
    base_modified_duration: float
    base_convexity: float
    scenarios: tuple[SensitivityScenario, ...]
    unsupported_mappings: tuple[UnsupportedMapping, ...]
    bond_terms: BondTerms
    base_yield: float
    base_spread_bps: int
    effective_spread_bps: int
    status: str

    @property
    def base_price(self) -> float:
        return self.base_dirty_price

    @property
    def base_duration(self) -> float:
        return self.base_modified_duration


def _require_supported_provenance(
    *,
    evidence_id: str,
    issuer: str,
    asset_id: str,
    rule_id: str,
    rule_version: str,
    valid_time: str,
    source_time: str,
) -> None:
    for name, value in (
        ("evidence_id", evidence_id),
        ("issuer", issuer),
        ("asset_id", asset_id),
        ("rule_id", rule_id),
        ("rule_version", rule_version),
        ("valid_time", valid_time),
        ("source_time", source_time),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required for valuation provenance")


def compute_sensitivity(
    bond_terms: BondTerms,
    base_yield: float,
    base_spread_bps: int,
    policy_result: PolicyResult,
    risk_channel_map: dict[str, str],
    *,
    issuer: str = "",
    asset_id: str = "",
    evidence_id: str = "",
    rule_id: str = "",
    rule_version: str = "",
    valid_time: str = "",
    source_time: str = "",
) -> ValuationSensitivityResult:
    """Reprice each supported channel and retain explicit no-adjustment rows."""
    if not math.isfinite(base_yield):
        raise ValueError("base_yield must be finite")
    if type(base_spread_bps) is not int:
        raise TypeError("base_spread_bps must be integer basis points")
    if not isinstance(risk_channel_map, dict):
        raise TypeError("risk_channel_map must be a dict")

    base = price_bond(bond_terms, base_yield, base_spread_bps)
    scenarios: list[SensitivityScenario] = []
    unsupported: list[UnsupportedMapping] = []

    if policy_result.adjustments or policy_result.unsupported_risk_factors:
        _require_supported_provenance(
            evidence_id=evidence_id,
            issuer=issuer,
            asset_id=asset_id,
            rule_id=rule_id,
            rule_version=rule_version,
            valid_time=valid_time,
            source_time=source_time,
        )

    supported_delta = 0
    recorded_unsupported: set[str] = set()
    for factor, delta_bps in policy_result.adjustments.items():
        if not isinstance(factor, str) or not factor:
            raise ValueError("risk factor names must be non-empty strings")
        if type(delta_bps) is not int:
            raise TypeError("spread adjustments must be integer basis points")
        channel = risk_channel_map.get(factor)
        if not channel:
            unsupported.append(
                UnsupportedMapping(
                    evidence_id=evidence_id,
                    issuer=issuer,
                    asset_id=asset_id,
                    risk_factor=factor,
                    rule_id=rule_id,
                    rule_version=rule_version,
                    base_spread_bps=base_spread_bps,
                    spread_delta_bps=0,
                    adjusted_spread_bps=base_spread_bps,
                    haircut_delta_bps=0,
                    decision_code=policy_result.decision_code,
                    valid_time=valid_time,
                    source_time=source_time,
                )
            )
            recorded_unsupported.add(factor)
            continue

        shocked = price_bond_with_spread_shock(
            bond_terms,
            base_yield,
            base_spread_bps,
            delta_bps,
        )
        supported_delta += delta_bps
        scenarios.append(
            SensitivityScenario(
                scenario_name=f"sensitivity_{channel}",
                evidence_id=evidence_id,
                issuer=issuer,
                asset_id=asset_id,
                risk_factor=factor,
                risk_channel=channel,
                rule_id=rule_id,
                rule_version=rule_version,
                units="bps",
                base_spread_bps=base_spread_bps,
                spread_delta_bps=delta_bps,
                adjusted_spread_bps=base_spread_bps + delta_bps,
                decision_code=policy_result.decision_code,
                day_count_convention=base.day_count_convention,
                compounding_convention=base.compounding_convention,
                settlement_date=bond_terms.settlement_date,
                maturity_date=bond_terms.maturity_date,
                coupon_frequency=bond_terms.payment_frequency,
                base_clean_price=base.clean_price,
                base_dirty_price=base.dirty_price,
                adjusted_clean_price=shocked.clean_price,
                adjusted_dirty_price=shocked.dirty_price,
                accrued_interest=shocked.accrued_interest,
                macaulay_duration=shocked.macaulay_duration,
                modified_duration=shocked.modified_duration,
                convexity=shocked.convexity,
                valid_time=valid_time,
                source_time=source_time,
            )
        )

    for factor in policy_result.unsupported_risk_factors:
        if factor in recorded_unsupported:
            continue
        unsupported.append(
            UnsupportedMapping(
                evidence_id=evidence_id,
                issuer=issuer,
                asset_id=asset_id,
                risk_factor=factor,
                rule_id=rule_id,
                rule_version=rule_version,
                base_spread_bps=base_spread_bps,
                spread_delta_bps=0,
                adjusted_spread_bps=base_spread_bps,
                haircut_delta_bps=0,
                decision_code=policy_result.decision_code,
                valid_time=valid_time,
                source_time=source_time,
            )
        )

    if policy_result.decision_code is DecisionCode.INSUFFICIENT_EVIDENCE:
        status = "insufficient_evidence"
        effective_spread = base_spread_bps
    elif not policy_result.adjustments and not policy_result.unsupported_risk_factors:
        status = "no_adjustment"
        effective_spread = base_spread_bps
    else:
        status = "evaluated"
        effective_spread = base_spread_bps + supported_delta

    return ValuationSensitivityResult(
        base_clean_price=base.clean_price,
        base_dirty_price=base.dirty_price,
        base_accrued_interest=base.accrued_interest,
        base_macaulay_duration=base.macaulay_duration,
        base_modified_duration=base.modified_duration,
        base_convexity=base.convexity,
        scenarios=tuple(scenarios),
        unsupported_mappings=tuple(unsupported),
        bond_terms=bond_terms,
        base_yield=base_yield,
        base_spread_bps=base_spread_bps,
        effective_spread_bps=effective_spread,
        status=status,
    )
