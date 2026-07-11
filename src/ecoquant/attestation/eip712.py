"""EIP-712 hashing helpers for RiskAttestationV1.

Uses genuine Ethereum Keccak-256 (NOT NIST SHA-3).
Ethereum uses the original Keccak-256 before NIST standardized it as SHA-3.
"""

from __future__ import annotations

import struct

from Crypto.Hash import keccak as _keccak

from .models import RiskAttestationV1


def keccak256(data: bytes) -> bytes:
    """Return the 32-byte Ethereum Keccak-256 digest.

    This is the genuine Ethereum Keccak, NOT NIST SHA-3.
    """
    k = _keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


# -- Domain separator --------------------------------------------------------

_EIP712_DOMAIN_TYPEHASH = keccak256(
    b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)

_RISK_ATTESTATION_V1_TYPEHASH = keccak256(
    b"RiskAttestationV1("
    b"uint16 schemaVersion,"
    b"bytes32 assetId,"
    b"uint64 asOf,"
    b"uint16 riskScoreBps,"
    b"uint16 confidenceBps,"
    b"uint16 recommendedHaircutBps,"
    b"bytes32 evidenceRoot,"
    b"bytes32 modelVersion,"
    b"uint8 decisionCode,"
    b"uint64 validUntil,"
    b"uint64 nonce,"
    b"address provider"
    b")"
)


def _abi_encode_uint256(value: int) -> bytes:
    """ABI-encode a uint256 as 32 big-endian bytes."""
    return value.to_bytes(32, byteorder="big")


def _abi_encode_address(address: str) -> bytes:
    """ABI-encode a hex address (with or without 0x prefix) as 32 bytes."""
    addr = address.lower().removeprefix("0x")
    return bytes(20) + bytes.fromhex(addr.rjust(40, "0"))


def _abi_encode_bytes32(value: bytes) -> bytes:
    """Pad or validate a 32-byte value."""
    if len(value) != 32:
        raise ValueError(f"Expected 32 bytes, got {len(value)}")
    return value


def compute_asset_id(isin: str) -> bytes:
    """Compute the asset ID: keccak256 of the uppercased ISIN."""
    return keccak256(isin.upper().encode("utf-8"))


def compute_model_version() -> bytes:
    """Compute the model version: keccak256 of b'ecoquant-temporal-v1'."""
    return keccak256(b"ecoquant-temporal-v1")


def eip712_domain_hash(
    name: str,
    version: str,
    chain_id: int,
    verifying_contract: str,
) -> bytes:
    """Compute the EIP-712 domain separator hash.

    ``keccak256(abi.encode(typeHash, keccak256(name), keccak256(version), chainId, verifyingContract))``
    """
    encoded = (
        _EIP712_DOMAIN_TYPEHASH
        + keccak256(name.encode("utf-8"))
        + keccak256(version.encode("utf-8"))
        + _abi_encode_uint256(chain_id)
        + _abi_encode_address(verifying_contract)
    )
    return keccak256(encoded)


def eip712_struct_hash(attestation: RiskAttestationV1) -> bytes:
    """Compute the EIP-712 struct hash for a ``RiskAttestationV1``.

    Fields are encoded in the exact order of the Solidity struct definition.
    """
    encoded = (
        _RISK_ATTESTATION_V1_TYPEHASH
        + _abi_encode_uint256(attestation.schema_version)
        + _abi_encode_bytes32(attestation.asset_id)
        + _abi_encode_uint256(attestation.as_of)
        + _abi_encode_uint256(attestation.risk_score_bps)
        + _abi_encode_uint256(attestation.confidence_bps)
        + _abi_encode_uint256(attestation.recommended_haircut_bps)
        + _abi_encode_bytes32(attestation.evidence_root)
        + _abi_encode_bytes32(attestation.model_version)
        + _abi_encode_uint256(attestation.decision_code)
        + _abi_encode_uint256(attestation.valid_until)
        + _abi_encode_uint256(attestation.nonce)
        + _abi_encode_address(attestation.provider)
    )
    return keccak256(encoded)


def eip712_digest(
    domain_hash: bytes,
    struct_hash: bytes,
) -> bytes:
    """Compute the final EIP-712 digest.

    ``keccak256(b"\\x19\\x01" + domainHash + structHash)``
    """
    return keccak256(b"\x19\x01" + domain_hash + struct_hash)
