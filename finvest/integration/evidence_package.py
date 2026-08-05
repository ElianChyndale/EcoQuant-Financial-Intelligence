"""FinVEST -> EcoQuant integration (A10).

Produces the evidence package that EcoQuant consumes, enforcing the hard
boundary: AI may retrieve, verify, calculate, explain, route for review, and
sign an evidence package. AI may NOT set credit spreads, approve lending,
transfer funds, liquidate collateral, or execute trades.

The package: answer/analysis, minimal evidence set, requirement coverage,
calculation program, temporal status, version status, conflict status,
sufficiency status, calibrated risk, review route, signed attestation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class EvidencePackage:
    """The bounded AI output consumed by EcoQuant's deterministic gate."""

    question: str
    answer: str | None
    evidence_set: tuple[str, ...]
    requirement_coverage: dict[str, bool]
    calculation_program: dict[str, object] | None
    temporal_status: dict[str, object]
    version_status: dict[str, object]
    conflict_status: dict[str, object]
    sufficiency_status: str  # SUPPORTED | PARTIAL | REFUTED | CONFLICTING | INSUFFICIENT
    calibrated_risk: float  # 0-1
    review_route: str  # auto | review
    attestation: dict[str, object] | None = None
    # Boundary: the package NEVER contains a spread, loan, transfer, or trade.
    prohibited_fields_present: bool = field(default=False, init=False)

    def validate_boundary(self) -> list[str]:
        """Return violations if the package crosses the AI/non-AI boundary."""
        violations: list[str] = []
        forbidden = ("spread_bps", "loan_amount", "transfer_amount", "liquidation", "trade")
        for field_name in forbidden:
            if field_name in self.__dict__ or field_name in (self.attestation or {}):
                violations.append(f"boundary violation: {field_name} present")
        return violations


def build_evidence_package(
    *,
    question: str,
    answer: str | None,
    evidence_set: tuple[str, ...],
    requirement_coverage: dict[str, bool],
    calculation_program: dict[str, object] | None,
    temporal_status: dict[str, object],
    version_status: dict[str, object],
    conflict_status: dict[str, object],
    sufficiency_status: str,
    calibrated_risk: float,
    review_route: str,
    sign: bool = True,
) -> EvidencePackage:
    """Assemble the evidence package; optionally sign an attestation."""
    package = EvidencePackage(
        question=question,
        answer=answer,
        evidence_set=evidence_set,
        requirement_coverage=requirement_coverage,
        calculation_program=calculation_program,
        temporal_status=temporal_status,
        version_status=version_status,
        conflict_status=conflict_status,
        sufficiency_status=sufficiency_status,
        calibrated_risk=calibrated_risk,
        review_route=review_route,
    )
    if sign and sufficiency_status == "SUPPORTED":
        package = EvidencePackage(
            **{**package.__dict__, "attestation": _sign_attestation(package)},
        )
    return package


def _sign_attestation(package: EvidencePackage) -> dict[str, object]:
    """Deterministic evidence-root attestation (not a financial action)."""
    evidence_root = hashlib.sha256(
        "|".join(sorted(package.evidence_set)).encode("utf-8")
    ).hexdigest()
    payload = {
        "schema_version": 1,
        "evidence_root": evidence_root,
        "sufficiency_status": package.sufficiency_status,
        "calibrated_risk_bps": min(10000, int(package.calibrated_risk * 10000)),
        "review_route": package.review_route,
        "provider": "finvest-evidence-pipeline-v1",
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["attestation_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload
