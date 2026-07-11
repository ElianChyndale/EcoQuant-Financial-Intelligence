"""RiskAttestationV1 frozen dataclass with strict validation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAttestationV1:
    """EIP-712-compatible risk attestation payload.

    Exact schema matching the Solidity struct:

        RiskAttestationV1(
            uint16 schemaVersion,
            bytes32 assetId,
            uint64 asOf,
            uint16 riskScoreBps,
            uint16 confidenceBps,
            uint16 recommendedHaircutBps,
            bytes32 evidenceRoot,
            bytes32 modelVersion,
            uint8 decisionCode,
            uint64 validUntil,
            uint64 nonce,
            address provider
        )

    All bps fields are basis points in the range [0, 10000].
    ``asset_id`` and ``evidence_root`` are 32-byte values (keccak256 digests).
    ``decision_code``: 0 = INSUFFICIENT, 1 = HUMAN_REVIEW, 2 = AUTO_REPORT.
    ``provider``: valid nonzero Ethereum address (checksummed or lowercase hex).
    ``valid_until``: must be >= ``as_of``.
    ``nonce``: must be a finite non-negative integer.
    """

    schema_version: int  # must be 1
    asset_id: bytes  # 32 bytes, keccak256 of uppercase ISIN
    as_of: int  # Unix seconds (uint64)
    risk_score_bps: int  # 0-10000 (uint16)
    confidence_bps: int  # 0-10000 (uint16)
    recommended_haircut_bps: int  # 0-10000 (uint16)
    evidence_root: bytes  # 32 bytes, Merkle root
    model_version: bytes  # 32 bytes, keccak256 of "ecoquant-temporal-v1"
    decision_code: int  # 0, 1, or 2 (uint8)
    valid_until: int  # Unix seconds (uint64)
    nonce: int  # uint64
    provider: str  # hex address (40 hex chars, with or without 0x)

    def __post_init__(self) -> None:
        # schemaVersion must be exactly 1
        if self.schema_version != 1:
            raise ValueError(
                f"schema_version must be 1, got {self.schema_version}"
            )

        # bps fields must be in [0, 10000] (uint16 range)
        _bps_fields = (
            ("risk_score_bps", self.risk_score_bps),
            ("confidence_bps", self.confidence_bps),
            ("recommended_haircut_bps", self.recommended_haircut_bps),
        )
        for name, value in _bps_fields:
            if not (0 <= value <= 10_000):
                raise ValueError(
                    f"{name} must be in [0, 10000], got {value}"
                )

        # decision_code must be 0, 1, or 2
        if self.decision_code not in (0, 1, 2):
            raise ValueError(
                f"decision_code must be 0, 1, or 2, got {self.decision_code}"
            )

        # bytes32 fields must be exactly 32 bytes
        _bytes32_fields = (
            ("asset_id", self.asset_id),
            ("evidence_root", self.evidence_root),
            ("model_version", self.model_version),
        )
        for name, value in _bytes32_fields:
            if not isinstance(value, bytes) or len(value) != 32:
                raise ValueError(
                    f"{name} must be exactly 32 bytes, got {len(value) if isinstance(value, bytes) else type(value)}"
                )

        # uint64 range checks: as_of, valid_until, nonce
        _uint64_fields = (
            ("as_of", self.as_of),
            ("valid_until", self.valid_until),
            ("nonce", self.nonce),
        )
        for name, value in _uint64_fields:
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric, got {type(value)}")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite, got {value}")
            if value < 0 or value > 0xFFFFFFFFFFFFFFFF:
                raise ValueError(
                    f"{name} must be in uint64 range [0, 2^64-1], got {value}"
                )

        # valid_until must be >= as_of
        if self.valid_until < self.as_of:
            raise ValueError(
                f"valid_until ({self.valid_until}) must be >= as_of ({self.as_of})"
            )

        # provider must be a valid nonzero Ethereum address
        _validate_address(self.provider, "provider")

        # provider must not be zero address
        addr_clean = self.provider.lower().removeprefix("0x")
        if int(addr_clean, 16) == 0:
            raise ValueError("provider must be a nonzero address")


def _validate_address(address: str, field_name: str) -> None:
    """Validate an Ethereum address.

    Must be 40 hex characters (with or without 0x prefix).
    Canonical handling: lowercase or EIP-55 checksummed.
    """
    if not isinstance(address, str):
        raise TypeError(f"{field_name} must be a string, got {type(address)}")

    addr = address.lower().removeprefix("0x")

    # Must be exactly 40 hex characters
    if len(addr) != 40:
        raise ValueError(
            f"{field_name} must be 40 hex characters (with or without 0x prefix), "
            f"got {len(addr)} chars"
        )

    # Must be valid hex
    if not re.match(r'^[0-9a-f]{40}$', addr):
        raise ValueError(
            f"{field_name} must contain only hex characters, got {address}"
        )
