"""Authoritative signing/recovery tests for RiskAttestationV1."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
from ecdsa import SECP256k1, VerifyingKey
from ecdsa.util import sigdecode_string

from ecoquant.attestation.eip712 import compute_asset_id, compute_model_version, keccak256
from ecoquant.attestation.models import RiskAttestationV1
from ecoquant.attestation.signing import (
    generate_ephemeral_keypair,
    recover_signer,
    sign_attestation,
    verify_provider,
    verify_signature,
)


CHAIN_ID = 31337
CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3"


def _attestation(provider: str) -> RiskAttestationV1:
    return RiskAttestationV1(
        schema_version=1,
        asset_id=compute_asset_id("IE00B4L5Y983"),
        as_of=1_720_000_000,
        risk_score_bps=3200,
        confidence_bps=8500,
        recommended_haircut_bps=150,
        evidence_root=keccak256(b"evidence-root"),
        model_version=compute_model_version(),
        decision_code=2,
        valid_until=1_720_100_000,
        nonce=42,
        provider=provider,
    )


@pytest.mark.parametrize(
    "field",
    (
        "schema_version",
        "as_of",
        "risk_score_bps",
        "confidence_bps",
        "recommended_haircut_bps",
        "decision_code",
        "valid_until",
        "nonce",
    ),
)
@pytest.mark.parametrize("bad_value", (True, 1.0))
def test_integer_fields_reject_bool_and_float(field: str, bad_value: object) -> None:
    keypair = generate_ephemeral_keypair()
    with pytest.raises(TypeError, match=field):
        replace(_attestation(keypair.address), **{field: bad_value})


def test_signing_requires_explicit_nonzero_domain() -> None:
    keypair = generate_ephemeral_keypair()
    attestation = _attestation(keypair.address)
    with pytest.raises(TypeError):
        sign_attestation(attestation, keypair.private_key)
    with pytest.raises(ValueError, match="nonzero"):
        sign_attestation(
            attestation,
            keypair.private_key,
            chain_id=CHAIN_ID,
            verifying_contract="0x0000000000000000000000000000000000000000",
        )


def test_signature_is_recoverable_and_provider_bound() -> None:
    keypair = generate_ephemeral_keypair()
    signed = sign_attestation(
        _attestation(keypair.address),
        keypair.private_key,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )
    assert len(signed.signature) == 65
    assert signed.signature[64] in (27, 28)
    assert recover_signer(
        signed,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    ) == keypair.address
    assert verify_signature(
        signed,
        keypair.address,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )
    assert verify_provider(
        signed,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )


@pytest.mark.parametrize("mutation", ("replace", "r", "s", "v", "truncate", "append", "zero_r", "zero_s", "high_s"))
def test_signature_tampering_is_rejected(mutation: str) -> None:
    keypair = generate_ephemeral_keypair()
    signed = sign_attestation(
        _attestation(keypair.address),
        keypair.private_key,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )
    signature = bytearray(signed.signature)
    if mutation == "replace":
        signature = bytearray(b"X" * 65)
    elif mutation == "r":
        signature[0] ^= 1
    elif mutation == "s":
        signature[32] ^= 1
    elif mutation == "v":
        signature[64] = 29
    elif mutation == "truncate":
        signature = signature[:-1]
    elif mutation == "append":
        signature.append(0)
    elif mutation == "zero_r":
        signature[:32] = b"\x00" * 32
    elif mutation == "zero_s":
        signature[32:64] = b"\x00" * 32
    elif mutation == "high_s":
        low_s = int.from_bytes(signature[32:64], "big")
        signature[32:64] = (SECP256k1.order - low_s).to_bytes(32, "big")

    tampered = replace(signed, signature=bytes(signature))
    assert not verify_signature(
        tampered,
        keypair.address,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )
    assert not verify_provider(
        tampered,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"chain_id": 1},
        {"verifying_contract": "0x0000000000000000000000000000000000000001"},
        {"domain_name": "WrongDomain"},
        {"domain_version": "2"},
    ),
)
def test_wrong_domain_binding_is_rejected(overrides: dict[str, object]) -> None:
    keypair = generate_ephemeral_keypair()
    signed = sign_attestation(
        _attestation(keypair.address),
        keypair.private_key,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )
    arguments: dict[str, object] = {
        "chain_id": CHAIN_ID,
        "verifying_contract": CONTRACT,
        "domain_name": "EcoQuantRiskAttestation",
        "domain_version": "1",
    }
    arguments.update(overrides)
    assert not verify_signature(signed, keypair.address, **arguments)


def test_tampered_attestation_and_wrong_provider_are_rejected() -> None:
    keypair = generate_ephemeral_keypair()
    signed = sign_attestation(
        _attestation(keypair.address),
        keypair.private_key,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )
    tampered = replace(
        signed,
        attestation=replace(signed.attestation, evidence_root=keccak256(b"tampered")),
    )
    assert not verify_provider(
        tampered,
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )
    assert not verify_signature(
        signed,
        "0x0000000000000000000000000000000000000001",
        chain_id=CHAIN_ID,
        verifying_contract=CONTRACT,
    )


def test_public_fixed_vector_uses_canonical_solidity_hashes() -> None:
    vector_path = Path(__file__).parents[1] / "fixtures" / "risk_attestation_v1_vector.json"
    vector = json.loads(vector_path.read_text(encoding="utf-8"))
    payload = vector["attestation"]
    attestation = RiskAttestationV1(
        schema_version=payload["schemaVersion"],
        asset_id=bytes.fromhex(payload["assetId"][2:]),
        as_of=payload["asOf"],
        risk_score_bps=payload["riskScoreBps"],
        confidence_bps=payload["confidenceBps"],
        recommended_haircut_bps=payload["recommendedHaircutBps"],
        evidence_root=bytes.fromhex(payload["evidenceRoot"][2:]),
        model_version=bytes.fromhex(payload["modelVersion"][2:]),
        decision_code=payload["decisionCode"],
        valid_until=payload["validUntil"],
        nonce=payload["nonce"],
        provider=payload["provider"],
    )
    from ecoquant.attestation.eip712 import eip712_digest, eip712_domain_hash, eip712_struct_hash

    domain_hash = eip712_domain_hash(
        vector["domain"]["name"],
        vector["domain"]["version"],
        vector["domain"]["chainId"],
        vector["domain"]["verifyingContract"],
    )
    struct_hash = eip712_struct_hash(attestation)
    digest = eip712_digest(domain_hash, struct_hash)
    assert domain_hash.hex() == vector["domainSeparator"][2:]
    assert struct_hash.hex() == vector["structHash"][2:]
    assert digest.hex() == vector["digest"][2:]
    assert vector["compiledSolidityVerification"] == "PROVEN_BY_CANONICAL_BRIDGE_TEST"


def test_task_7b_report_records_compiled_interoperability() -> None:
    report_path = (
        Path(__file__).parents[2]
        / ".superpowers"
        / "remediation"
        / "task-7b-sol-repair-report.md"
    )
    report = report_path.read_text(encoding="utf-8")

    assert "PENDING GBL Tasks 12/14" not in report
    assert "252d195" in report
    assert "132a187" in report
    assert "forge test --ffi --match-path test/CanonicalBridge.t.sol -vv" in report
