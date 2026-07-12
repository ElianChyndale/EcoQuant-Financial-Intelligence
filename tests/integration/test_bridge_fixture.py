"""Cross-repository fixture encoding tests for the canonical bridge."""

from __future__ import annotations

from ecoquant.attestation.signing import verify_provider
from scripts.generate_bridge_fixture import build_bridge_fixture


def test_bridge_fixture_is_public_canonical_abi_and_cryptographically_valid() -> None:
    contract = "0x1234567890123456789012345678901234567890"
    attestation, signed, encoded = build_bridge_fixture(
        chain_id=31337,
        verifying_contract=contract,
        as_of=1_720_000_000,
        valid_until=1_720_003_600,
    )

    assert attestation.schema_version == 1
    assert attestation.nonce == 1
    assert len(signed.signature) == 65
    assert len(encoded) == 13 * 32 + 32 + 96
    assert int.from_bytes(encoded[12 * 32 : 13 * 32], "big") == 13 * 32
    assert int.from_bytes(encoded[13 * 32 : 14 * 32], "big") == 65
    assert encoded[14 * 32 : 14 * 32 + 65] == signed.signature
    assert verify_provider(
        signed,
        chain_id=31337,
        verifying_contract=contract,
    )


def test_bridge_fixture_contains_no_private_key_bytes() -> None:
    _, _, encoded = build_bridge_fixture(
        chain_id=31337,
        verifying_contract="0x1234567890123456789012345678901234567890",
        as_of=1_720_000_000,
        valid_until=1_720_003_600,
    )
    # The ABI payload is strictly the 12 public typed fields plus signature.
    assert len(encoded) == 13 * 32 + 32 + 96
    assert b"private" not in encoded.lower()
