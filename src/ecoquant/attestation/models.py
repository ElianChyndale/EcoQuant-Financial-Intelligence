"""RiskAttestationV1 frozen dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAttestationV1:
    """EIP-712-compatible risk attestation payload.

    All bps fields are basis points in the range [0, 10000].
    ``asset_id`` and ``evidence_root`` are 32-byte values (keccak256 digests).
    ``decision_code``: 0 = accept, 1 = flag, 2 = reject.
    """

    schema_version: int  # must be 1
    asset_id: bytes  # 32 bytes, keccak256 of uppercase ISIN
    as_of: int  # Unix seconds
    risk_score_bps: int  # 0-10000
    confidence_bps: int  # 0-10000
    recommended_haircut_bps: int  # 0-10000
    evidence_root: bytes  # 32 bytes, Merkle root
    model_version: bytes  # 32 bytes, keccak256 of "ecoquant-temporal-v1"
    decision_code: int  # 0, 1, or 2
    valid_until: int  # Unix seconds
    nonce: int
    provider: str  # hex address

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                f"schema_version must be 1, got {self.schema_version}"
            )
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
        if self.decision_code not in (0, 1, 2):
            raise ValueError(
                f"decision_code must be 0, 1, or 2, got {self.decision_code}"
            )
