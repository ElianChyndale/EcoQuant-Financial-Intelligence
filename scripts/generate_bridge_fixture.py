#!/usr/bin/env python3
"""Emit a public ABI fixture signed for a deployed RiskOracleAdapter.

The command writes one 0x-prefixed ABI byte string to stdout for Foundry FFI.
The ephemeral private key remains in process memory and is never serialized.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from ecoquant.attestation.eip712 import compute_asset_id, compute_model_version, keccak256
from ecoquant.attestation.models import RiskAttestationV1
from ecoquant.attestation.signing import SignedAttestation, generate_ephemeral_keypair, sign_attestation


def _uint_word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _address_word(address: str) -> bytes:
    return bytes(12) + bytes.fromhex(address.removeprefix("0x"))


def _encode_fixture(attestation: RiskAttestationV1, signature: bytes) -> bytes:
    """ABI encode the twelve static struct fields followed by dynamic bytes."""
    head = b"".join(
        (
            _uint_word(attestation.schema_version),
            attestation.asset_id,
            _uint_word(attestation.as_of),
            _uint_word(attestation.risk_score_bps),
            _uint_word(attestation.confidence_bps),
            _uint_word(attestation.recommended_haircut_bps),
            attestation.evidence_root,
            attestation.model_version,
            _uint_word(attestation.decision_code),
            _uint_word(attestation.valid_until),
            _uint_word(attestation.nonce),
            _address_word(attestation.provider),
            _uint_word(13 * 32),
        )
    )
    padding = (32 - len(signature) % 32) % 32
    return head + _uint_word(len(signature)) + signature + bytes(padding)


def build_bridge_fixture(
    *,
    chain_id: int,
    verifying_contract: str,
    as_of: int,
    valid_until: int,
    domain_name: str = "EcoQuantRiskAttestation",
    domain_version: str = "1",
) -> tuple[RiskAttestationV1, SignedAttestation, bytes]:
    """Create one canonical public bridge fixture with an ephemeral provider."""
    keypair = generate_ephemeral_keypair()
    attestation = RiskAttestationV1(
        schema_version=1,
        asset_id=compute_asset_id("XS1234567890"),
        as_of=as_of,
        risk_score_bps=5000,
        confidence_bps=8500,
        recommended_haircut_bps=200,
        evidence_root=keccak256(b"ecoquant-bridge-evidence-v1"),
        model_version=compute_model_version(),
        decision_code=2,
        valid_until=valid_until,
        nonce=1,
        provider=keypair.address,
    )
    signed = sign_attestation(
        attestation,
        keypair.private_key,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
        domain_name=domain_name,
        domain_version=domain_version,
    )
    return attestation, signed, _encode_fixture(attestation, signed.signature)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain-id", type=int, required=True)
    parser.add_argument("--verifying-contract", required=True)
    parser.add_argument("--as-of", type=int, required=True)
    parser.add_argument("--valid-until", type=int, required=True)
    parser.add_argument("--domain-name", default="EcoQuantRiskAttestation")
    parser.add_argument("--domain-version", default="1")
    arguments = parser.parse_args()
    _, _, encoded = build_bridge_fixture(
        chain_id=arguments.chain_id,
        verifying_contract=arguments.verifying_contract,
        as_of=arguments.as_of,
        valid_until=arguments.valid_until,
        domain_name=arguments.domain_name,
        domain_version=arguments.domain_version,
    )
    sys.stdout.write("0x" + encoded.hex())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
