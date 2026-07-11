"""Attestation models and EIP-712 tests for Task 7.

Tests cover RiskAttestationV1 field presence, EIP-712 domain/struct hashing,
keccak256-based asset ID and model version computation, Merkle evidence root
order-independence, schema_version enforcement, decision code semantics, and
basis-point range validation.
"""

from __future__ import annotations

import dataclasses

import pytest

from ecoquant.attestation.eip712 import (
    compute_asset_id,
    compute_model_version,
    eip712_domain_hash,
    eip712_struct_hash,
    keccak256,
)
from ecoquant.attestation.merkle import evidence_merkle_root
from ecoquant.attestation.models import RiskAttestationV1
from ecoquant.uncertainty.decision import DecisionCode


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
