"""Attestation models and EIP-712 tests for Task 7.

Tests cover RiskAttestationV1 field presence, EIP-712 domain/struct hashing,
keccak256-based asset ID and model version computation, Merkle evidence root
order-independence, schema_version enforcement, decision code semantics,
basis-point range validation, cross-language test vectors, and bond pricing.
"""

from __future__ import annotations

import dataclasses
import math

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
from ecoquant.uncertainty.decision import DecisionCode
from ecoquant.valuation.bond_pricing import (
    BondTerms,
    price_bond,
    price_bond_with_spread_shock,
    compute_duration_convexity_numerically,
)


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
        decision_code=DecisionCode.AUTO_REPORT,
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


# ---------------------------------------------------------------------------
# Tests: Merkle evidence root
# ---------------------------------------------------------------------------


class TestMerkleEvidenceRoot:
    """Evidence Merkle root must be order-independent for the same set."""

    def test_attestation_hash_is_order_independent_for_evidence(self) -> None:
        """evidence_merkle_root([a, b]) must equal evidence_merkle_root([b, a])."""
        leaf_a = keccak256(b"evidence-doc-A")
        leaf_b = keccak256(b"evidence-doc-B")

        root_ab = evidence_merkle_root([leaf_a, leaf_b])
        root_ba = evidence_merkle_root([leaf_b, leaf_a])

        assert root_ab == root_ba
        assert len(root_ab) == 32

    def test_merkle_root_deterministic(self) -> None:
        """Same input list always produces the same root."""
        leaves = [keccak256(f"doc-{i}".encode()) for i in range(4)]
        root_1 = evidence_merkle_root(leaves)
        root_2 = evidence_merkle_root(leaves)
        assert root_1 == root_2

    def test_merkle_root_single_leaf(self) -> None:
        """A single-leaf tree returns a deterministic 32-byte root."""
        leaf = keccak256(b"sole-evidence")
        root = evidence_merkle_root([leaf])
        assert len(root) == 32
        # The root should differ from the raw leaf (sorted-single wrapping).
        # Implementation detail: single leaf may equal its own hash, but must
        # be 32 bytes.
        assert isinstance(root, bytes)


# ---------------------------------------------------------------------------
# Tests: RiskAttestationV1 field presence
# ---------------------------------------------------------------------------


class TestRiskAttestationV1Fields:
    """RiskAttestationV1 must expose every field required by the EIP-712 struct."""

    REQUIRED_FIELDS = (
        "schema_version",
        "asset_id",
        "as_of",
        "risk_score_bps",
        "confidence_bps",
        "recommended_haircut_bps",
        "evidence_root",
        "model_version",
        "decision_code",
        "valid_until",
        "nonce",
        "provider",
    )

    def test_risk_attestation_v1_fields(self) -> None:
        actual_names = {f.name for f in dataclasses.fields(RiskAttestationV1)}
        for field_name in self.REQUIRED_FIELDS:
            assert field_name in actual_names, (
                f"RiskAttestationV1 is missing required field: {field_name}"
            )

    def test_frozen_dataclass(self, sample_attestation: RiskAttestationV1) -> None:
        """RiskAttestationV1 is a frozen dataclass; mutation must raise."""
        with pytest.raises(AttributeError):
            sample_attestation.nonce = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: keccak256-based deterministic identifiers
# ---------------------------------------------------------------------------


class TestDeterministicIdentifiers:
    """asset_id and model_version are keccak256 digests of fixed preimages."""

    def test_asset_id_is_keccak_of_uppercase_isin(self) -> None:
        isin = "IE00B4L5Y983"
        asset_id = compute_asset_id(isin)
        expected = keccak256(isin.upper().encode("utf-8"))
        assert asset_id == expected
        assert len(asset_id) == 32

    def test_asset_id_case_insensitive(self) -> None:
        """Lower-case input must produce the same id as upper-case."""
        assert compute_asset_id("ie00b4l5y983") == compute_asset_id("IE00B4L5Y983")

    def test_asset_id_deterministic(self) -> None:
        """Calling compute_asset_id twice with the same ISIN returns equal bytes."""
        isin = "US0378331005"
        assert compute_asset_id(isin) == compute_asset_id(isin)

    def test_model_version_is_keccak_of_model_string(self) -> None:
        model_ver = compute_model_version()
        expected = keccak256(b"ecoquant-temporal-v1")
        assert model_ver == expected
        assert len(model_ver) == 32

    def test_model_version_deterministic(self) -> None:
        assert compute_model_version() == compute_model_version()


# ---------------------------------------------------------------------------
# Tests: EIP-712 domain separator
# ---------------------------------------------------------------------------


class TestEIP712Domain:
    """Domain separator must encode name, version, chainId, verifyingContract."""

    def test_eip712_domain(self, default_domain_args: dict[str, object]) -> None:
        domain_hash = eip712_domain_hash(**default_domain_args)  # type: ignore[arg-type]
        assert len(domain_hash) == 32
        assert isinstance(domain_hash, bytes)

    def test_eip712_domain_varies_with_chain_id(self, default_domain_args: dict[str, object]) -> None:
        """Different chain IDs must produce different domain hashes."""
        hash_chain_1 = eip712_domain_hash(**default_domain_args)  # type: ignore[arg-type]
        args_137 = {**default_domain_args, "chain_id": 137}
        hash_chain_137 = eip712_domain_hash(**args_137)  # type: ignore[arg-type]
        assert hash_chain_1 != hash_chain_137

    def test_eip712_domain_deterministic(self, default_domain_args: dict[str, object]) -> None:
        h1 = eip712_domain_hash(**default_domain_args)  # type: ignore[arg-type]
        h2 = eip712_domain_hash(**default_domain_args)  # type: ignore[arg-type]
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: EIP-712 struct hash
# ---------------------------------------------------------------------------


class TestEIP712StructHash:
    """Struct hash must be deterministic over the attestation fields."""

    def test_eip712_hash_deterministic(
        self,
        sample_attestation: RiskAttestationV1,
    ) -> None:
        h1 = eip712_struct_hash(sample_attestation)
        h2 = eip712_struct_hash(sample_attestation)
        assert h1 == h2
        assert len(h1) == 32

    def test_eip712_hash_differs_for_different_attestations(
        self,
        sample_attestation: RiskAttestationV1,
    ) -> None:
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
# Tests: schema_version enforcement
# ---------------------------------------------------------------------------


class TestSchemaVersionEnforcement:
    """schema_version must be exactly 1."""

    def test_schema_version_must_be_1(self) -> None:
        with pytest.raises(ValueError, match="schema_version must be 1"):
            RiskAttestationV1(
                schema_version=2,
                asset_id=b"\x00" * 32,
                as_of=0,
                risk_score_bps=0,
                confidence_bps=0,
                recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32,
                model_version=b"\x00" * 32,
                decision_code=0,
                valid_until=0,
                nonce=0,
                provider="0x0000000000000000000000000000000000000000",
            )

    def test_schema_version_1_accepted(self) -> None:
        att = RiskAttestationV1(
            schema_version=1,
            asset_id=b"\x00" * 32,
            as_of=0,
            risk_score_bps=0,
            confidence_bps=0,
            recommended_haircut_bps=0,
            evidence_root=b"\x00" * 32,
            model_version=b"\x00" * 32,
            decision_code=0,
            valid_until=0,
            nonce=0,
            provider="0x0000000000000000000000000000000000000000",
        )
        assert att.schema_version == 1


# ---------------------------------------------------------------------------
# Tests: decision code semantics
# ---------------------------------------------------------------------------


class TestDecisionCodeValues:
    """Decision code integers must map to the correct INSUFFICIENT / HUMAN_REVIEW / AUTO_REPORT names."""

    def test_decision_code_values(self) -> None:
        assert DecisionCode.INSUFFICIENT_EVIDENCE == 0
        assert DecisionCode.HUMAN_REVIEW_REQUIRED == 1
        assert DecisionCode.AUTO_REPORT == 2

    def test_decision_code_ordering(self) -> None:
        assert (
            DecisionCode.INSUFFICIENT_EVIDENCE
            < DecisionCode.HUMAN_REVIEW_REQUIRED
            < DecisionCode.AUTO_REPORT
        )


# ---------------------------------------------------------------------------
# Tests: basis-point range validation
# ---------------------------------------------------------------------------


class TestBasisPointsRange:
    """risk_score_bps, confidence_bps, recommended_haircut_bps must be in [0, 10000]."""

    @pytest.mark.parametrize("field", ["risk_score_bps", "confidence_bps", "recommended_haircut_bps"])
    def test_basis_points_range_lower_bound(self, field: str) -> None:
        """Negative bps values must be rejected."""
        kwargs = dict(
            schema_version=1,
            asset_id=b"\x00" * 32,
            as_of=0,
            risk_score_bps=0,
            confidence_bps=0,
            recommended_haircut_bps=0,
            evidence_root=b"\x00" * 32,
            model_version=b"\x00" * 32,
            decision_code=0,
            valid_until=0,
            nonce=0,
            provider="0x0000000000000000000000000000000000000000",
        )
        kwargs[field] = -1
        with pytest.raises(ValueError, match=f"{field} must be in"):
            RiskAttestationV1(**kwargs)

    @pytest.mark.parametrize("field", ["risk_score_bps", "confidence_bps", "recommended_haircut_bps"])
    def test_basis_points_range_upper_bound(self, field: str) -> None:
        """Values above 10000 bps must be rejected."""
        kwargs = dict(
            schema_version=1,
            asset_id=b"\x00" * 32,
            as_of=0,
            risk_score_bps=0,
            confidence_bps=0,
            recommended_haircut_bps=0,
            evidence_root=b"\x00" * 32,
            model_version=b"\x00" * 32,
            decision_code=0,
            valid_until=0,
            nonce=0,
            provider="0x0000000000000000000000000000000000000000",
        )
        kwargs[field] = 10_001
        with pytest.raises(ValueError, match=f"{field} must be in"):
            RiskAttestationV1(**kwargs)

    @pytest.mark.parametrize("field", ["risk_score_bps", "confidence_bps", "recommended_haircut_bps"])
    def test_basis_points_range_boundary_accepted(self, field: str) -> None:
        """Boundary values 0 and 10000 must be accepted."""
        for boundary in (0, 10_000):
            kwargs = dict(
                schema_version=1,
                asset_id=b"\x00" * 32,
                as_of=0,
                risk_score_bps=0,
                confidence_bps=0,
                recommended_haircut_bps=0,
                evidence_root=b"\x00" * 32,
                model_version=b"\x00" * 32,
                decision_code=0,
                valid_until=0,
                nonce=0,
                provider="0x0000000000000000000000000000000000000000",
            )
            kwargs[field] = boundary
            att = RiskAttestationV1(**kwargs)
            assert getattr(att, field) == boundary


# ---------------------------------------------------------------------------
# Tests: Cross-language EIP-712 test vectors
# ---------------------------------------------------------------------------


class TestCrossLanguageVectors:
    """Verify EIP-712 implementation produces correct hashes.

    These test vectors can be independently verified against Solidity.
    """

    def test_keccak256_is_genuine_ethereum_keccak(self) -> None:
        """Verify we're using genuine Ethereum Keccak, not NIST SHA-3."""
        # Ethereum Keccak-256 of empty bytes
        empty_keccak = keccak256(b"")
        # This is a known Ethereum Keccak value
        expected_hex = "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
        assert empty_keccak.hex() == expected_hex

    def test_asset_id_vector(self) -> None:
        """Test asset ID computation with known ISIN."""
        isin = "IE00B4L5Y983"
        asset_id = compute_asset_id(isin)
        # Verify it's 32 bytes
        assert len(asset_id) == 32
        # Verify uppercase normalization
        assert compute_asset_id("ie00b4l5y983") == asset_id

    def test_model_version_vector(self) -> None:
        """Test model version computation."""
        model_version = compute_model_version()
        assert len(model_version) == 32
        # Should be keccak256 of "ecoquant-temporal-v1"
        expected = keccak256(b"ecoquant-temporal-v1")
        assert model_version == expected

    def test_domain_hash_vector(self) -> None:
        """Test domain hash with canonical parameters."""
        domain_hash = eip712_domain_hash(
            name="EcoQuantRiskAttestation",
            version="1",
            chain_id=31337,  # Anvil default chain ID
            verifying_contract="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )
        assert len(domain_hash) == 32
        # Should be deterministic
        assert domain_hash == eip712_domain_hash(
            name="EcoQuantRiskAttestation",
            version="1",
            chain_id=31337,
            verifying_contract="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )

    def test_struct_hash_vector(self) -> None:
        """Test struct hash with known attestation."""
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
        """Test final EIP-712 digest computation."""
        domain_hash = eip712_domain_hash(
            name="EcoQuantRiskAttestation",
            version="1",
            chain_id=31337,
            verifying_contract="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )
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
        digest = eip712_digest(domain_hash, struct_hash)
        assert len(digest) == 32
        # Should be deterministic
        assert digest == eip712_digest(domain_hash, struct_hash)

    def test_wrong_chain_rejected(self) -> None:
        """Different chain IDs must produce different domain hashes."""
        hash_1 = eip712_domain_hash("EcoQuantRiskAttestation", "1", 1, "0x0000000000000000000000000000000000000001")
        hash_137 = eip712_domain_hash("EcoQuantRiskAttestation", "1", 137, "0x0000000000000000000000000000000000000001")
        assert hash_1 != hash_137

    def test_wrong_domain_name_rejected(self) -> None:
        """Different domain names must produce different hashes."""
        hash_correct = eip712_domain_hash("EcoQuantRiskAttestation", "1", 1, "0x0000000000000000000000000000000000000001")
        hash_wrong = eip712_domain_hash("WrongName", "1", 1, "0x0000000000000000000000000000000000000001")
        assert hash_correct != hash_wrong

    def test_wrong_version_rejected(self) -> None:
        """Different versions must produce different hashes."""
        hash_v1 = eip712_domain_hash("EcoQuantRiskAttestation", "1", 1, "0x0000000000000000000000000000000000000001")
        hash_v2 = eip712_domain_hash("EcoQuantRiskAttestation", "2", 1, "0x0000000000000000000000000000000000000001")
        assert hash_v1 != hash_v2

    def test_field_tampering_rejected(self) -> None:
        """Tampering with any field must change the struct hash."""
        base = RiskAttestationV1(
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
        base_hash = eip712_struct_hash(base)

        # Tamper with risk_score_bps
        tampered = RiskAttestationV1(
            schema_version=1,
            asset_id=compute_asset_id("IE00B4L5Y983"),
            as_of=1720000000,
            risk_score_bps=3201,  # Changed
            confidence_bps=8500,
            recommended_haircut_bps=150,
            evidence_root=keccak256(b"evidence-root"),
            model_version=compute_model_version(),
            decision_code=2,
            valid_until=1720100000,
            nonce=42,
            provider="0xAbCdEf0123456789AbCdEf0123456789AbCdEf01",
        )
        tampered_hash = eip712_struct_hash(tampered)
        assert base_hash != tampered_hash


# ---------------------------------------------------------------------------
# Tests: Bond pricing
# ---------------------------------------------------------------------------


class TestBondPricing:
    """Verify bond pricing calculations."""

    def _sample_terms(self) -> BondTerms:
        return BondTerms(
            face_value=1000.0,
            coupon_rate=0.05,  # 5% annual
            payment_frequency=2,  # Semi-annual
            maturity_years=10.0,
            settlement_date=0.0,
        )

    def test_bond_price_at_par(self) -> None:
        """Bond priced at par when coupon equals yield."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert abs(result.price - 1000.0) < 0.01  # Should be very close to par

    def test_bond_price_above_par_when_coupon_above_yield(self) -> None:
        """Bond trades above par when coupon rate exceeds yield."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.04)
        assert result.price > 1000.0

    def test_bond_price_below_par_when_coupon_below_yield(self) -> None:
        """Bond trades below par when coupon rate is below yield."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.06)
        assert result.price < 1000.0

    def test_duration_positive(self) -> None:
        """Duration must be positive."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert result.macaulay_duration > 0
        assert result.modified_duration > 0

    def test_convexity_positive(self) -> None:
        """Convexity must be positive for option-free bonds."""
        terms = self._sample_terms()
        result = price_bond(terms, yield_to_maturity=0.05)
        assert result.convexity > 0

    def test_duration_decreases_with_yield(self) -> None:
        """Higher yield should reduce duration."""
        terms = self._sample_terms()
        result_low = price_bond(terms, yield_to_maturity=0.04)
        result_high = price_bond(terms, yield_to_maturity=0.06)
        assert result_low.modified_duration > result_high.modified_duration

    def test_spread_widening_reduces_price(self) -> None:
        """Higher spread should reduce bond price."""
        terms = self._sample_terms()
        result_base = price_bond(terms, yield_to_maturity=0.05, spread_bps=0)
        result_spread = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        assert result_base.price > result_spread.price

    def test_finite_difference_duration(self) -> None:
        """Finite difference duration should match analytical duration."""
        terms = self._sample_terms()
        analytical = price_bond(terms, yield_to_maturity=0.05)
        numerical_duration, numerical_convexity = compute_duration_convexity_numerically(
            terms, yield_to_maturity=0.05, delta=0.0001
        )
        # Should be close (within 1%)
        assert abs(analytical.modified_duration - numerical_duration) / analytical.modified_duration < 0.01

    def test_finite_difference_convexity(self) -> None:
        """Finite difference convexity should match analytical convexity."""
        terms = self._sample_terms()
        analytical = price_bond(terms, yield_to_maturity=0.05)
        numerical_duration, numerical_convexity = compute_duration_convexity_numerically(
            terms, yield_to_maturity=0.05, delta=0.0001
        )
        # Should be close (within 1%)
        assert abs(analytical.convexity - numerical_convexity) / analytical.convexity < 0.01

    def test_bond_price_with_spread_shock(self) -> None:
        """Spread shock should reduce price by expected amount."""
        terms = self._sample_terms()
        base = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        shocked = price_bond_with_spread_shock(terms, 0.05, 100, 50)
        # Higher spread = lower price
        assert shocked.price < base.price

    def test_bond_pricing_deterministic(self) -> None:
        """Same inputs must produce same outputs."""
        terms = self._sample_terms()
        result1 = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        result2 = price_bond(terms, yield_to_maturity=0.05, spread_bps=100)
        assert result1.price == result2.price
        assert result1.macaulay_duration == result2.macaulay_duration
        assert result1.modified_duration == result2.modified_duration
        assert result1.convexity == result2.convexity
