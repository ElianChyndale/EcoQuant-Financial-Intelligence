"""Attestation models, EIP-712, signing, and bond pricing tests.

Tests cover:
- RiskAttestationV1 strict field validation
- EIP-712 domain/struct hashing
- secp256k1 signing and recovery
- Provider verification
- Expiry checking
- Merkle evidence root
- Bond pricing with settlement-aware cash flows
- Input validation
- Independent fixed vectors
- Adversarial cases
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from ecoquant.attestation.eip712 import (
    compute_asset_id,
    compute_model_version,
    eip712_domain_hash,
    eip712_struct_hash,
    eip712_digest,
    keccak256,
)
from ecoquant.attestation.merkle import evidence_merkle_root
from ecoquant.attestation.models import RiskAttestationV1
from ecoquant.attestation.signing import (
    generate_ephemeral_keypair,
    sign_attestation,
    verify_signature,
    verify_provider,
    check_expiry,
    SignedAttestation,
)
from ecoquant.uncertainty.decision import DecisionCode
from ecoquant.valuation.bond_pricing import (
    BondTerms,
    BondPricingResult,
    price_bond,
    price_bond_with_spread_shock,
    compute_duration_convexity_numerically,
)

_CHAIN_ID = 31337
_VERIFYING_CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
_DOMAIN = {"chain_id": _CHAIN_ID, "verifying_contract": _VERIFYING_CONTRACT}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_attestation() -> RiskAttestationV1:
    """A fully populated RiskAttestationV1 for testing."""
    return RiskAttestationV1(
        schema_version=1,
        asset_id=compute_asset_id("IE00B4L5Y983"),
        as_of=1_720_000_000,
        risk_score_bps=3200,
        confidence_bps=8500,
        recommended_haircut_bps=150,
        evidence_root=keccak256(b"evidence-root"),
        model_version=compute_model_version(),
        decision_code=int(DecisionCode.AUTO_REPORT),
        valid_until=1_720_100_000,
        nonce=42,
        provider="0xAbCdEf0123456789AbCdEf0123456789AbCdEf01",
    )


@pytest.fixture()
def default_domain_args() -> dict[str, object]:
    """Canonical EIP-712 domain parameters."""
    return {
        "name": "EcoQuantRiskAttestation",
        "version": "1",
        "chain_id": 1,
        "verifying_contract": "0x0000000000000000000000000000000000000001",
    }


@pytest.fixture()
def keypair() -> tuple[bytes, str]:
    """Generate an ephemeral key pair for signing tests."""
    kp = generate_ephemeral_keypair()
    return kp.private_key, kp.address


# ---------------------------------------------------------------------------
# Tests: Merkle evidence root
# ---------------------------------------------------------------------------


class TestMerkleEvidenceRoot:
    """Evidence Merkle root must be order-independent for the same set."""

    def test_attestation_hash_is_order_independent_for_evidence(self) -> None:
        leaf_a = keccak256(b"evidence-doc-A")
        leaf_b = keccak256(b"evidence-doc-B")
        root_ab = evidence_merkle_root([leaf_a, leaf_b])
        root_ba = evidence_merkle_root([leaf_b, leaf_a])
        assert root_ab == root_ba


# ---------------------------------------------------------------------------
# Tests: EIP-712 domain separator
# ---------------------------------------------------------------------------


class TestEIP712DomainSeparator:
    """Domain separator must be deterministic and sensitive to all parameters."""

    def test_domain_hash_deterministic(self, default_domain_args: dict) -> None:
        h1 = eip712_domain_hash(**default_domain_args)
        h2 = eip712_domain_hash(**default_domain_args)
        assert h1 == h2
        assert len(h1) == 32


# ---------------------------------------------------------------------------
# Tests: EIP-712 struct hash
# ---------------------------------------------------------------------------


class TestEIP712StructHash:
    """Struct hash must be deterministic over the attestation fields."""

    def test_eip712_hash_deterministic(self, sample_attestation: RiskAttestationV1) -> None:
        h1 = eip712_struct_hash(sample_attestation)
        h2 = eip712_struct_hash(sample_attestation)
        assert h1 == h2
        assert len(h1) == 32

    def test_eip712_hash_differs_for_different_attestations(self, sample_attestation: RiskAttestationV1) -> None:
        modified = RiskAttestationV1(
            schema_version=1,
            asset_id=compute_asset_id("US0378331005"),
            as_of=sample_attestation.as_of,
            risk_score_bps=sample_attestation.risk_score_bps,
            confidence_bps=sample_attestation.confidence_bps,
            recommended_haircut_bps=sample_attestation.recommended_haircut_bps,
            evidence_root=sample_attestation.evidence_root,
            model_version=sample_attestation.model_version,
            decision_code=sample_attestation.decision_code,
            valid_until=sample_attestation.valid_until,
            nonce=sample_attestation.nonce,
            provider=sample_attestation.provider,
        )
        assert eip712_struct_hash(sample_attestation) != eip712_struct_hash(modified)


# ---------------------------------------------------------------------------
# Tests: Strict model validation
# ---------------------------------------------------------------------------


class TestStrictModelValidation:
    """RiskAttestationV1 must validate all fields at construction time."""

    def test_schema_version_must_be_1(self) -> None:
        with pytest.raises(ValueError, match="schema_version must be 1"):
            RiskAttestationV1(
                schema_version=2, asset_id=b"\x00" * 32, as_of=0,
                risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
                decision_code=0, valid_until=0, nonce=0,
                provider="0x0000000000000000000000000000000000000001",
            )

    def test_uint64_range_enforced(self) -> None:
        """Values exceeding uint64 must be rejected."""
        with pytest.raises(ValueError, match="uint64"):
            RiskAttestationV1(
                schema_version=1, asset_id=b"\x00" * 32,
                as_of=0xFFFFFFFFFFFFFFFF + 1,  # Exceeds uint64
                risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
                decision_code=0, valid_until=0, nonce=0,
                provider="0x0000000000000000000000000000000000000001",
            )

    def test_bytes32_exact_length_enforced(self) -> None:
        """Malformed bytes32 (not 32 bytes) must be rejected."""
        with pytest.raises(ValueError, match="32 bytes"):
            RiskAttestationV1(
                schema_version=1, asset_id=b"\x00" * 31,  # Wrong length
                as_of=0, risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
                decision_code=0, valid_until=0, nonce=0,
                provider="0x0000000000000000000000000000000000000001",
            )

    def test_provider_zero_address_rejected(self) -> None:
        """Zero address provider must be rejected."""
        with pytest.raises(ValueError, match="nonzero"):
            RiskAttestationV1(
                schema_version=1, asset_id=b"\x00" * 32, as_of=0,
                risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
                decision_code=0, valid_until=0, nonce=0,
                provider="0x0000000000000000000000000000000000000000",
            )

    def test_provider_must_be_valid_address(self) -> None:
        """Invalid provider strings must be rejected."""
        with pytest.raises(ValueError, match="40 hex"):
            RiskAttestationV1(
                schema_version=1, asset_id=b"\x00" * 32, as_of=0,
                risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
                decision_code=0, valid_until=0, nonce=0,
                provider="not-an-address",
            )

    def test_valid_until_must_be_gte_as_of(self) -> None:
        """valid_until < as_of must be rejected."""
        with pytest.raises(ValueError, match="valid_until.*as_of"):
            RiskAttestationV1(
                schema_version=1, asset_id=b"\x00" * 32, as_of=1000,
                risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
                decision_code=0, valid_until=999, nonce=0,
                provider="0x0000000000000000000000000000000000000001",
            )

    def test_finite_timestamps_required(self) -> None:
        """Non-finite timestamps must be rejected."""
        with pytest.raises(TypeError, match="integer"):
            RiskAttestationV1(
                schema_version=1, asset_id=b"\x00" * 32,
                as_of=float("inf"),
                risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
                decision_code=0, valid_until=0, nonce=0,
                provider="0x0000000000000000000000000000000000000001",
            )


# ---------------------------------------------------------------------------
# Tests: Signing and recovery
# ---------------------------------------------------------------------------


class TestSigningAndVerification:
    """secp256k1 signing, verification, and provider checks."""

    def test_sign_and_verify(self, sample_attestation: RiskAttestationV1) -> None:
        """Sign an attestation and verify the signer."""
        kp = generate_ephemeral_keypair()
        signed = sign_attestation(sample_attestation, kp.private_key, **_DOMAIN)
        assert signed.signer_address.lower() == kp.address.lower()
        assert verify_signature(signed, kp.address, **_DOMAIN) is True

    def test_provider_verification(self, sample_attestation: RiskAttestationV1) -> None:
        """Provider must match the signer."""
        kp = generate_ephemeral_keypair()
        att = RiskAttestationV1(
            schema_version=1,
            asset_id=sample_attestation.asset_id,
            as_of=sample_attestation.as_of,
            risk_score_bps=sample_attestation.risk_score_bps,
            confidence_bps=sample_attestation.confidence_bps,
            recommended_haircut_bps=sample_attestation.recommended_haircut_bps,
            evidence_root=sample_attestation.evidence_root,
            model_version=sample_attestation.model_version,
            decision_code=sample_attestation.decision_code,
            valid_until=sample_attestation.valid_until,
            nonce=sample_attestation.nonce,
            provider=kp.address,
        )
        signed = sign_attestation(att, kp.private_key, **_DOMAIN)
        assert verify_provider(signed, **_DOMAIN) is True

    def test_wrong_provider_fails_verification(self, sample_attestation: RiskAttestationV1) -> None:
        """Provider mismatch must fail verification."""
        kp = generate_ephemeral_keypair()
        signed = sign_attestation(sample_attestation, kp.private_key, **_DOMAIN)
        # sample_attestation has a different provider than kp.address
        assert verify_provider(signed, **_DOMAIN) is False

    def test_expiry_check_valid(self) -> None:
        """Non-expired attestation should pass expiry check."""
        att = RiskAttestationV1(
            schema_version=1, asset_id=b"\x00" * 32, as_of=1000,
            risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
            evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
            decision_code=0, valid_until=2000, nonce=0,
            provider="0x0000000000000000000000000000000000000001",
        )
        assert check_expiry(att, current_time=1500) is True

    def test_expiry_check_expired(self) -> None:
        """Expired attestation should fail expiry check."""
        att = RiskAttestationV1(
            schema_version=1, asset_id=b"\x00" * 32, as_of=1000,
            risk_score_bps=0, confidence_bps=0, recommended_haircut_bps=0,
            evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
            decision_code=0, valid_until=2000, nonce=0,
            provider="0x0000000000000000000000000000000000000001",
        )
        assert check_expiry(att, current_time=2001) is False

    def test_signature_deterministic(self, sample_attestation: RiskAttestationV1) -> None:
        """Same key and attestation must produce same signature (RFC 6979)."""
        kp = generate_ephemeral_keypair()
        signed1 = sign_attestation(sample_attestation, kp.private_key, **_DOMAIN)
        signed2 = sign_attestation(sample_attestation, kp.private_key, **_DOMAIN)
        assert signed1.signature == signed2.signature

    def test_different_keys_produce_different_signatures(self, sample_attestation: RiskAttestationV1) -> None:
        """Different keys must produce different signatures."""
        kp1 = generate_ephemeral_keypair()
        kp2 = generate_ephemeral_keypair()
        signed1 = sign_attestation(sample_attestation, kp1.private_key, **_DOMAIN)
        signed2 = sign_attestation(sample_attestation, kp2.private_key, **_DOMAIN)
        assert signed1.signature != signed2.signature

    def test_different_attestations_produce_different_signatures(self) -> None:
        """Different attestations must produce different signatures."""
        kp = generate_ephemeral_keypair()
        att1 = RiskAttestationV1(
            schema_version=1, asset_id=b"\x00" * 32, as_of=1000,
            risk_score_bps=100, confidence_bps=200, recommended_haircut_bps=50,
            evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
            decision_code=0, valid_until=2000, nonce=1,
            provider=kp.address,
        )
        att2 = RiskAttestationV1(
            schema_version=1, asset_id=b"\x00" * 32, as_of=1000,
            risk_score_bps=101, confidence_bps=200, recommended_haircut_bps=50,
            evidence_root=b"\x00" * 32, model_version=b"\x00" * 32,
            decision_code=0, valid_until=2000, nonce=1,
            provider=kp.address,
        )
        signed1 = sign_attestation(att1, kp.private_key, **_DOMAIN)
        signed2 = sign_attestation(att2, kp.private_key, **_DOMAIN)
        assert signed1.signature != signed2.signature

    def test_signature_is_65_bytes(self, sample_attestation: RiskAttestationV1) -> None:
        """Signature must be canonical recoverable r, s, v bytes."""
        kp = generate_ephemeral_keypair()
        signed = sign_attestation(sample_attestation, kp.private_key, **_DOMAIN)
        assert len(signed.signature) == 65
        assert signed.signature[64] in (27, 28)

    def test_low_s_normalization(self, sample_attestation: RiskAttestationV1) -> None:
        """Signature s value must be in the lower half of the curve order."""
        from ecdsa import SECP256k1
        kp = generate_ephemeral_keypair()
        signed = sign_attestation(sample_attestation, kp.private_key, **_DOMAIN)
        s = int.from_bytes(signed.signature[32:64], "big")
        assert s <= SECP256k1.order // 2


# ---------------------------------------------------------------------------
# Tests: Cross-language EIP-712 test vectors
# ---------------------------------------------------------------------------


class TestCrossLanguageVectors:
    """Provisional Solidity-compatible EIP-712 vectors.

    Labelled as provisional until Tasks 12/14 compile and verify on-chain.
    """

    def test_keccak256_is_genuine_ethereum_keccak(self) -> None:
        empty_keccak = keccak256(b"")
        expected_hex = "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
        assert empty_keccak.hex() == expected_hex

    def test_asset_id_vector(self) -> None:
        asset_id = compute_asset_id("IE00B4L5Y983")
        assert len(asset_id) == 32
        assert compute_asset_id("ie00b4l5y983") == asset_id

    def test_model_version_vector(self) -> None:
        model_version = compute_model_version()
        assert len(model_version) == 32
        assert model_version == keccak256(b"ecoquant-temporal-v1")

    def test_domain_hash_vector(self) -> None:
        domain_hash = eip712_domain_hash(
            name="EcoQuantRiskAttestation",
            version="1",
            chain_id=31337,
            verifying_contract="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )
        assert len(domain_hash) == 32

    def test_struct_hash_vector(self) -> None:
        attestation = RiskAttestationV1(
            schema_version=1,
            asset_id=compute_asset_id("IE00B4L5Y983"),
            as_of=1720000000,
            risk_score_bps=3200,
            confidence_bps=8500,
            recommended_haircut_bps=150,
            evidence_root=keccak256(b"evidence-root"),
            model_version=compute_model_version(),
            decision_code=2,
            valid_until=1720100000,
            nonce=42,
            provider="0xAbCdEf0123456789AbCdEf0123456789AbCdEf01",
        )
        struct_hash = eip712_struct_hash(attestation)
        assert len(struct_hash) == 32

    def test_final_digest_vector(self) -> None:
        domain_hash = eip712_domain_hash(
            name="EcoQuantRiskAttestation", version="1",
            chain_id=31337,
            verifying_contract="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )
        attestation = RiskAttestationV1(
            schema_version=1,
            asset_id=compute_asset_id("IE00B4L5Y983"),
            as_of=1720000000, risk_score_bps=3200, confidence_bps=8500,
            recommended_haircut_bps=150, evidence_root=keccak256(b"evidence-root"),
            model_version=compute_model_version(), decision_code=2,
            valid_until=1720100000, nonce=42,
            provider="0xAbCdEf0123456789AbCdEf0123456789AbCdEf01",
        )
        struct_hash = eip712_struct_hash(attestation)
        digest = eip712_digest(domain_hash, struct_hash)
        assert len(digest) == 32
        assert digest == eip712_digest(domain_hash, struct_hash)

    def test_wrong_chain_rejected(self) -> None:
        hash_1 = eip712_domain_hash("EcoQuantRiskAttestation", "1", 1, "0x0000000000000000000000000000000000000001")
        hash_137 = eip712_domain_hash("EcoQuantRiskAttestation", "1", 137, "0x0000000000000000000000000000000000000001")
        assert hash_1 != hash_137

    def test_wrong_domain_name_rejected(self) -> None:
        hash_correct = eip712_domain_hash("EcoQuantRiskAttestation", "1", 1, "0x0000000000000000000000000000000000000001")
        hash_wrong = eip712_domain_hash("WrongName", "1", 1, "0x0000000000000000000000000000000000000001")
        assert hash_correct != hash_wrong

    def test_wrong_version_rejected(self) -> None:
        hash_v1 = eip712_domain_hash("EcoQuantRiskAttestation", "1", 1, "0x0000000000000000000000000000000000000001")
        hash_v2 = eip712_domain_hash("EcoQuantRiskAttestation", "2", 1, "0x0000000000000000000000000000000000000001")
        assert hash_v1 != hash_v2

    def test_field_tampering_rejected(self) -> None:
        base = RiskAttestationV1(
            schema_version=1, asset_id=compute_asset_id("IE00B4L5Y983"),
            as_of=1720000000, risk_score_bps=3200, confidence_bps=8500,
            recommended_haircut_bps=150, evidence_root=keccak256(b"evidence-root"),
            model_version=compute_model_version(), decision_code=2,
            valid_until=1720100000, nonce=42,
            provider="0xAbCdEf0123456789AbCdEf0123456789AbCdEf01",
        )
        base_hash = eip712_struct_hash(base)

        tampered = RiskAttestationV1(
            schema_version=1, asset_id=compute_asset_id("IE00B4L5Y983"),
            as_of=1720000000, risk_score_bps=3201, confidence_bps=8500,
            recommended_haircut_bps=150, evidence_root=keccak256(b"evidence-root"),
            model_version=compute_model_version(), decision_code=2,
            valid_until=1720100000, nonce=42,
            provider="0xAbCdEf0123456789AbCdEf0123456789AbCdEf01",
        )
        assert base_hash != eip712_struct_hash(tampered)


# ---------------------------------------------------------------------------
# Tests: Bond pricing with settlement-aware cash flows
# ---------------------------------------------------------------------------


class TestBondPricing:
    """Verify bond pricing with settlement awareness."""

    def _sample_terms(self) -> BondTerms:
        return BondTerms(
            face_value=1000.0,
            coupon_rate=0.05,
            payment_frequency=2,
            maturity_years=10.0,
            settlement_date=date(2025, 1, 15),
            issue_date=date(2025, 1, 1),
        )

    def test_bond_price_at_par(self) -> None:
        """Bond priced at par when coupon equals yield."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert abs(result.clean_price - 1000.0) < 1.0  # Close to par

    def test_bond_price_above_par_when_coupon_above_yield(self) -> None:
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.04)
        assert result.clean_price > 1000.0

    def test_bond_price_below_par_when_coupon_below_yield(self) -> None:
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.06)
        assert result.clean_price < 1000.0

    def test_duration_positive(self) -> None:
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert result.macaulay_duration > 0
        assert result.modified_duration > 0

    def test_convexity_positive(self) -> None:
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert result.convexity > 0

    def test_duration_decreases_with_yield(self) -> None:
        terms = self._sample_terms()
        result_low = price_bond(terms, yield_to_maturity=0.04)
        result_high = price_bond(terms, yield_to_maturity=0.06)
        assert result_low.modified_duration > result_high.modified_duration

    def test_spread_widening_reduces_price(self) -> None:
        terms = self._sample_terms()
        result_base = price_bond(terms, yield_to_maturity=0.05, spread_bps=0)
        result_spread = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        assert result_base.clean_price > result_spread.clean_price

    def test_finite_difference_duration(self) -> None:
        terms = self._sample_terms()
        analytical = price_bond(terms, yield_to_maturity=0.05)
        numerical_duration, _ = compute_duration_convexity_numerically(
            terms, yield_to_maturity=0.05, delta=0.0001
        )
        assert abs(analytical.modified_duration - numerical_duration) / analytical.modified_duration < 0.01

    def test_finite_difference_convexity(self) -> None:
        terms = self._sample_terms()
        analytical = price_bond(terms, yield_to_maturity=0.05)
        _, numerical_convexity = compute_duration_convexity_numerically(
            terms, yield_to_maturity=0.05, delta=0.0001
        )
        assert abs(analytical.convexity - numerical_convexity) / analytical.convexity < 0.01

    def test_bond_price_with_spread_shock(self) -> None:
        terms = self._sample_terms()
        base = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        shocked = price_bond_with_spread_shock(terms, 0.05, 100, 50)
        assert shocked.clean_price < base.clean_price

    def test_bond_pricing_deterministic(self) -> None:
        terms = self._sample_terms()
        result1 = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        result2 = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        assert result1.price == result2.price
        assert result1.modified_duration == result2.modified_duration

    def test_settlement_date_is_used(self) -> None:
        """settlement_date must affect pricing (not be ignored)."""
        terms_early = BondTerms(
            face_value=1000.0, coupon_rate=0.05, payment_frequency=2,
            maturity_years=10.0,
            settlement_date=date(2025, 1, 5),
            issue_date=date(2025, 1, 1),
        )
        terms_late = BondTerms(
            face_value=1000.0, coupon_rate=0.05, payment_frequency=2,
            maturity_years=10.0,
            settlement_date=date(2025, 6, 15),
            issue_date=date(2025, 1, 1),
        )
        result_early = price_bond(terms_early, yield_to_maturity=0.05)
        result_late = price_bond(terms_late, yield_to_maturity=0.05)
        # Different settlement dates must produce different dirty prices
        # (due to accrued interest)
        assert result_early.accrued_interest != result_late.accrued_interest

    def test_accrued_interest_positive(self) -> None:
        """Accrued interest must be non-negative."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert result.accrued_interest >= 0.0

    def test_dirty_equals_clean_plus_accrued(self) -> None:
        """Dirty price = clean price + accrued interest."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert abs(result.price - (result.clean_price + result.accrued_interest)) < 1e-10


# ---------------------------------------------------------------------------
# Tests: Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Bond pricing must reject invalid inputs."""

    def _valid_terms(self) -> BondTerms:
        return BondTerms(
            face_value=1000.0, coupon_rate=0.05, payment_frequency=2,
            maturity_years=10.0,
            settlement_date=date(2025, 1, 15),
            issue_date=date(2025, 1, 1),
        )

    def test_rejects_zero_face_value(self) -> None:
        terms = BondTerms(
            face_value=0, coupon_rate=0.05, payment_frequency=2,
            maturity_years=10.0,
            settlement_date=date(2025, 1, 15),
            issue_date=date(2025, 1, 1),
        )
        with pytest.raises(ValueError, match="face_value"):
            price_bond(terms, 0.05)

    def test_rejects_negative_face_value(self) -> None:
        terms = BondTerms(
            face_value=-1000, coupon_rate=0.05, payment_frequency=2,
            maturity_years=10.0,
            settlement_date=date(2025, 1, 15),
            issue_date=date(2025, 1, 1),
        )
        with pytest.raises(ValueError, match="face_value"):
            price_bond(terms, 0.05)

    def test_rejects_invalid_frequency(self) -> None:
        terms = BondTerms(
            face_value=1000, coupon_rate=0.05, payment_frequency=3,
            maturity_years=10.0,
            settlement_date=date(2025, 1, 15),
            issue_date=date(2025, 1, 1),
        )
        with pytest.raises(ValueError, match="payment_frequency"):
            price_bond(terms, 0.05)

    def test_rejects_non_finite_yield(self) -> None:
        terms = self._valid_terms()
        with pytest.raises(ValueError, match="yield"):
            price_bond(terms, float("inf"))

    def test_rejects_settlement_before_issue(self) -> None:
        terms = BondTerms(
            face_value=1000, coupon_rate=0.05, payment_frequency=2,
            maturity_years=10.0,
            settlement_date=date(2024, 1, 1),
            issue_date=date(2025, 1, 1),
        )
        with pytest.raises(ValueError, match="settlement"):
            price_bond(terms, 0.05)

    def test_rejects_zero_maturity(self) -> None:
        terms = BondTerms(
            face_value=1000, coupon_rate=0.05, payment_frequency=2,
            maturity_years=0,
            settlement_date=date(2025, 1, 15),
            issue_date=date(2025, 1, 1),
        )
        with pytest.raises(ValueError, match="maturity"):
            price_bond(terms, 0.05)
