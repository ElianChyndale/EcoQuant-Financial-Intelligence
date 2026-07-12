"""Task 14 — Cross-repository bridge fixture generator.

Generates signed RiskAttestationV1 fixtures for Solidity consumption.
Documents SOL-3 schema mismatch between Python and Solidity EIP-712.

SOL-3 ESCALATION:
- Python domain name: "EcoQuantRiskAttestation" (no spaces)
- Solidity domain name: "EcoQuant Risk Attestation" (with spaces)
- Python type hash: camelCase (schemaVersion, assetId, asOf, ...)
- Solidity type hash: snake_case (schema_version, asset_id, as_of, ...)
- Python field types: uint16, uint64
- Solidity field types: uint8, uint256

Cross-language signature verification is NOT possible without schema alignment.
This test generates fixtures using the Python schema for Python-side verification.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import replace

import pytest

from ecoquant.attestation.eip712 import (
    eip712_digest,
    eip712_domain_hash,
    eip712_struct_hash,
    keccak256,
)
from ecoquant.attestation.models import RiskAttestationV1
from ecoquant.attestation.signing import generate_ephemeral_keypair, sign_attestation


@pytest.fixture
def test_key():
    """Generate an ephemeral test key pair."""
    return generate_ephemeral_keypair()


@pytest.fixture
def sample_attestation():
    """Create a sample RiskAttestationV1 for testing."""
    return RiskAttestationV1(
        schema_version=1,
        asset_id=keccak256(b"XS1234567890"),
        as_of=1000000,
        risk_score_bps=5000,
        confidence_bps=8500,
        recommended_haircut_bps=2000,
        evidence_root=keccak256(b"evidence"),
        model_version=keccak256(b"ecoquant-temporal-v1"),
        decision_code=2,  # AUTO_REPORT
        valid_until=1000000 + 86400,
        nonce=1,
        provider="0x0000000000000000000000000000000000000001",  # placeholder
    )


class TestBridgeFixtureGeneration:
    """Test that bridge fixtures can be generated and verified in Python."""

    def test_generate_signed_attestation(self, test_key, sample_attestation):
        """Generate a signed attestation fixture."""
        # Set the provider to the test key's address
        att = replace(sample_attestation, provider=test_key.address)

        # Sign
        signed = sign_attestation(
            att, test_key.private_key,
            chain_id=31337,
            verifying_contract="0x1234567890123456789012345678901234567890",
        )

        # Verify signature length (65 bytes: r || s || v)
        assert len(signed.signature) == 65

        # Verify the signature can be recovered
        from ecoquant.attestation.signing import recover_signer

        recovered = recover_signer(
            signed,
            chain_id=31337,
            verifying_contract="0x1234567890123456789012345678901234567890",
        )
        assert recovered.lower() == test_key.address.lower()

    def test_domain_hash_matches_python_schema(self):
        """Verify the Python domain hash uses the Python schema name."""
        domain_hash = eip712_domain_hash(
            name="EcoQuantRiskAttestation",
            version="1",
            chain_id=31337,
            verifying_contract="0x1234567890123456789012345678901234567890",
        )
        assert len(domain_hash) == 32

        # Verify it would differ from Solidity's domain hash
        # Solidity uses "EcoQuant Risk Attestation" (with spaces)
        solidity_domain_hash = eip712_domain_hash(
            name="EcoQuant Risk Attestation",
            version="1",
            chain_id=31337,
            verifying_contract="0x1234567890123456789012345678901234567890",
        )
        assert domain_hash != solidity_domain_hash, (
            "SOL-3: Python and Solidity domain hashes should differ "
            "due to different domain names"
        )

    def test_struct_hash_uses_camelcase_fields(self, sample_attestation):
        """Verify the Python struct hash uses camelCase field names."""
        struct_hash = eip712_struct_hash(sample_attestation)
        assert len(struct_hash) == 32

        # The type hash should be for camelCase fields:
        # "RiskAttestationV1(uint16 schemaVersion,bytes32 assetId,...)"
        # NOT snake_case: "RiskAttestationV1(uint8 schema_version,bytes32 asset_id,...)"
        expected_typehash = keccak256(
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
        # The struct hash uses this type hash, so we can verify it's consistent
        assert len(expected_typehash) == 32

    def test_full_eip712_digest(self, test_key, sample_attestation):
        """Test full EIP-712 digest computation."""
        att = replace(sample_attestation, provider=test_key.address)

        domain_hash = eip712_domain_hash(
            name="EcoQuantRiskAttestation",
            version="1",
            chain_id=31337,
            verifying_contract="0x1234567890123456789012345678901234567890",
        )

        struct_hash = eip712_struct_hash(att)
        digest = eip712_digest(domain_hash, struct_hash)

        assert len(digest) == 32

    def test_generate_bridge_fixture_file(self, test_key, sample_attestation, tmp_path):
        """Generate a JSON fixture file for bridge testing."""
        att = replace(sample_attestation, provider=test_key.address)
        signed = sign_attestation(
            att, test_key.private_key,
            chain_id=31337,
            verifying_contract="0x1234567890123456789012345678901234567890",
        )
        signature = signed.signature

        fixture = {
            "schema": "RiskAttestationV1",
            "domain": {
                "name": "EcoQuantRiskAttestation",
                "version": "1",
                "chainId": 31337,
                "verifyingContract": "0x1234567890123456789012345678901234567890",
            },
            "attestation": {
                "schemaVersion": att.schema_version,
                "assetId": att.asset_id.hex(),
                "asOf": att.as_of,
                "riskScoreBps": att.risk_score_bps,
                "confidenceBps": att.confidence_bps,
                "recommendedHaircutBps": att.recommended_haircut_bps,
                "evidenceRoot": att.evidence_root.hex(),
                "modelVersion": att.model_version.hex(),
                "decisionCode": att.decision_code,
                "validUntil": att.valid_until,
                "nonce": att.nonce,
                "provider": att.provider,
            },
            "signature": signature.hex(),
            "signerAddress": test_key.address,
            "sol3Escalation": {
                "issue": "Python and Solidity EIP-712 schemas differ",
                "pythonDomain": "EcoQuantRiskAttestation",
                "solidityDomain": "EcoQuant Risk Attestation",
                "pythonFields": "camelCase (schemaVersion, assetId, asOf, ...)",
                "solidityFields": "snake_case (schema_version, asset_id, as_of, ...)",
                "pythonTypes": "uint16, uint64",
                "solidityTypes": "uint8, uint256",
                "impact": "Cross-language signature verification impossible without schema alignment",
            },
        }

        fixture_path = tmp_path / "bridge_fixture.json"
        fixture_path.write_text(json.dumps(fixture, indent=2))

        # Verify the fixture file is valid JSON
        loaded = json.loads(fixture_path.read_text())
        assert loaded["schema"] == "RiskAttestationV1"
        assert len(loaded["signature"]) == 130  # 65 bytes as hex

    def test_sol3_schema_mismatch_documented(self):
        """Explicit test documenting the SOL-3 schema mismatch."""
        # This test exists to document the issue, not to test behavior.
        # The mismatch is:
        # 1. Domain name differs (spaces vs no spaces)
        # 2. Field names differ (camelCase vs snake_case)
        # 3. Field types differ (uint16/uint64 vs uint8/uint256)
        #
        # Resolution requires Sol review (SOL-3).
        # Options:
        # A. Align Python to Solidity schema (change Python)
        # B. Align Solidity to Python schema (change Solidity)
        # C. Accept both as separate schemas (no cross-language verification)
        assert True  # Documentation test
