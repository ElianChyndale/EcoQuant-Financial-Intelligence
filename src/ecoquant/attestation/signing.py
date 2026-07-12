"""Recoverable EIP-712 signing for RiskAttestationV1.

Signatures use the canonical Ethereum wire form r || s || v where v is 27 or
28. Only low-s signatures are accepted. Verification recomputes the runtime
domain and struct digest, recovers the public key, and compares the derived
Ethereum address; stored signer metadata is never trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ecdsa import BadSignatureError, SECP256k1, SigningKey, VerifyingKey
from ecdsa.numbertheory import SquareRootError
from ecdsa.util import sigdecode_string, sigencode_string

from .eip712 import eip712_digest, eip712_domain_hash, eip712_struct_hash, keccak256
from .models import RiskAttestationV1, _validate_address


CANONICAL_DOMAIN_NAME = "EcoQuantRiskAttestation"
CANONICAL_DOMAIN_VERSION = "1"
_ZERO_ADDRESS = "0x" + "0" * 40


@dataclass(frozen=True)
class SignedAttestation:
    """A public signed attestation and reproducibility metadata."""

    attestation: RiskAttestationV1
    signature: bytes
    domain_hash: bytes
    struct_hash: bytes
    digest: bytes
    signer_address: str
    public_key: bytes


@dataclass(frozen=True)
class EphemeralKeyPair:
    """An in-memory test keypair. Private bytes must never be serialized."""

    private_key: bytes
    address: str


def generate_ephemeral_keypair() -> EphemeralKeyPair:
    """Generate an ephemeral secp256k1 keypair for local tests/fixtures."""
    signing_key = SigningKey.generate(curve=SECP256k1)
    return EphemeralKeyPair(
        private_key=signing_key.to_string(),
        address=_public_key_to_address(signing_key.get_verifying_key()),
    )


def _public_key_to_address(verifying_key: VerifyingKey) -> str:
    public_bytes = verifying_key.to_string()
    return "0x" + keccak256(public_bytes)[-20:].hex()


def _validate_domain(chain_id: int, verifying_contract: str) -> None:
    if type(chain_id) is not int:
        raise TypeError("chain_id must be an integer")
    if chain_id <= 0:
        raise ValueError("chain_id must be positive")
    _validate_address(verifying_contract, "verifying_contract")
    if verifying_contract.lower() == _ZERO_ADDRESS:
        raise ValueError("verifying_contract must be nonzero")


def _hash_attestation(
    attestation: RiskAttestationV1,
    *,
    chain_id: int,
    verifying_contract: str,
    domain_name: str,
    domain_version: str,
) -> tuple[bytes, bytes, bytes]:
    _validate_domain(chain_id, verifying_contract)
    domain_hash = eip712_domain_hash(
        domain_name,
        domain_version,
        chain_id,
        verifying_contract,
    )
    struct_hash = eip712_struct_hash(attestation)
    return domain_hash, struct_hash, eip712_digest(domain_hash, struct_hash)


def _recovery_candidates(signature64: bytes, digest: bytes) -> tuple[VerifyingKey, ...]:
    try:
        candidates = VerifyingKey.from_public_key_recovery_with_digest(
            signature64,
            digest,
            curve=SECP256k1,
            sigdecode=sigdecode_string,
            allow_truncate=True,
        )
    except (BadSignatureError, ValueError, AssertionError, SquareRootError):
        return ()
    return tuple(candidates)


def sign_attestation(
    attestation: RiskAttestationV1,
    private_key: bytes,
    *,
    chain_id: int,
    verifying_contract: str,
    domain_name: str = CANONICAL_DOMAIN_NAME,
    domain_version: str = CANONICAL_DOMAIN_VERSION,
) -> SignedAttestation:
    """Sign an attestation using RFC6979 and return a recoverable signature."""
    domain_hash, struct_hash, digest = _hash_attestation(
        attestation,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
        domain_name=domain_name,
        domain_version=domain_version,
    )
    if not isinstance(private_key, bytes) or len(private_key) != 32:
        raise ValueError("private_key must be exactly 32 bytes")
    signing_key = SigningKey.from_string(private_key, curve=SECP256k1)
    verifying_key = signing_key.get_verifying_key()
    signer_address = _public_key_to_address(verifying_key)
    signature64 = signing_key.sign_digest_deterministic(
        digest,
        sigencode=sigencode_string,
        allow_truncate=True,
    )
    r, s = sigdecode_string(signature64, SECP256k1.order)
    if s > SECP256k1.order // 2:
        s = SECP256k1.order - s
    signature64 = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    candidates = _recovery_candidates(signature64, digest)
    recovery_id = next(
        (
            index
            for index, candidate in enumerate(candidates[:2])
            if candidate.to_string() == verifying_key.to_string()
        ),
        None,
    )
    if recovery_id is None:
        raise RuntimeError("could not derive Ethereum recovery id for signature")

    signature = signature64 + bytes([27 + recovery_id])
    return SignedAttestation(
        attestation=attestation,
        signature=signature,
        domain_hash=domain_hash,
        struct_hash=struct_hash,
        digest=digest,
        signer_address=signer_address,
        public_key=verifying_key.to_string(),
    )


def recover_signer(
    signed: SignedAttestation,
    *,
    chain_id: int,
    verifying_contract: str,
    domain_name: str = CANONICAL_DOMAIN_NAME,
    domain_version: str = CANONICAL_DOMAIN_VERSION,
) -> str:
    """Recover the signer address or raise ValueError for invalid input."""
    domain_hash, struct_hash, digest = _hash_attestation(
        signed.attestation,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
        domain_name=domain_name,
        domain_version=domain_version,
    )
    if domain_hash != signed.domain_hash or struct_hash != signed.struct_hash or digest != signed.digest:
        raise ValueError("signed hash metadata does not match the attestation and domain")
    if not isinstance(signed.signature, bytes) or len(signed.signature) != 65:
        raise ValueError("signature must be exactly 65 bytes")

    r = int.from_bytes(signed.signature[:32], "big")
    s = int.from_bytes(signed.signature[32:64], "big")
    v = signed.signature[64]
    if not 1 <= r < SECP256k1.order:
        raise ValueError("signature r is outside the secp256k1 range")
    if not 1 <= s <= SECP256k1.order // 2:
        raise ValueError("signature s must be nonzero and low-s")
    if v not in (27, 28):
        raise ValueError("signature v must be 27 or 28")

    candidates = _recovery_candidates(signed.signature[:64], digest)
    recovery_id = v - 27
    if recovery_id >= len(candidates):
        raise ValueError("signature recovery id has no public-key candidate")
    verifying_key = candidates[recovery_id]
    try:
        valid = verifying_key.verify_digest(
            signed.signature[:64],
            digest,
            sigdecode=sigdecode_string,
            allow_truncate=True,
        )
    except BadSignatureError as error:
        raise ValueError("signature verification failed") from error
    if not valid:
        raise ValueError("signature verification failed")
    return _public_key_to_address(verifying_key)


def verify_signature(
    signed: SignedAttestation,
    signer_address: str,
    *,
    chain_id: int,
    verifying_contract: str,
    domain_name: str = CANONICAL_DOMAIN_NAME,
    domain_version: str = CANONICAL_DOMAIN_VERSION,
) -> bool:
    """Return whether the recovered signer equals the expected address."""
    try:
        _validate_address(signer_address, "signer_address")
        recovered = recover_signer(
            signed,
            chain_id=chain_id,
            verifying_contract=verifying_contract,
            domain_name=domain_name,
            domain_version=domain_version,
        )
    except (TypeError, ValueError, BadSignatureError):
        return False
    return recovered.lower() == signer_address.lower()


def verify_provider(
    signed: SignedAttestation,
    *,
    chain_id: int,
    verifying_contract: str,
    domain_name: str = CANONICAL_DOMAIN_NAME,
    domain_version: str = CANONICAL_DOMAIN_VERSION,
) -> bool:
    """Cryptographically recover and compare the attestation provider."""
    return verify_signature(
        signed,
        signed.attestation.provider,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
        domain_name=domain_name,
        domain_version=domain_version,
    )


def check_expiry(
    attestation: RiskAttestationV1,
    *,
    current_time: int | None = None,
) -> bool:
    """Return whether the attestation is valid at the supplied Unix time."""
    if current_time is None:
        current_time = int(datetime.now(timezone.utc).timestamp())
    if type(current_time) is not int:
        raise TypeError("current_time must be an integer")
    return attestation.as_of <= current_time <= attestation.valid_until
