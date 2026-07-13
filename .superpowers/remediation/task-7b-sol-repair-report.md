# Task 7B Cryptographic Repair Report

**Date:** 2026-07-12
**Status:** Python implementation and compiled interoperability reviewed; fresh overall review required

## Canonical contract

- Struct fields and order remain the approved RiskAttestationV1 schema.
- Every integer field requires exact Python `int`; bool and float are rejected.
- Solidity uint8/uint16/uint64 bounds, bps bounds, bytes32 lengths, decision
  codes, nonzero provider, and `validUntil >= asOf` are enforced.
- Domain name/version are `EcoQuantRiskAttestation` / `1`.
- Runtime chain ID and a nonzero verifying-contract address are mandatory.
- Ethereum Keccak-256, the exact type string, ABI-width padding, and
  `0x1901 || domainSeparator || structHash` remain the hashing contract.

## Signing and recovery

Signing uses secp256k1 with RFC6979, EIP-2 low-s normalization, and the canonical
65-byte wire form:

```text
r (32 bytes) || s (32 bytes) || v (1 byte, 27 or 28)
```

The recovery ID is selected only after low-s normalization. Verification
recomputes the runtime domain and struct digest, validates r/s/v, recovers the
public key, verifies the signature, derives the Ethereum address from Keccak of
the 64-byte public key, and compares that recovered address. The diagnostic
`signer_address` field is not trusted.

## RED/GREEN evidence

Initial RED:

```text
ImportError: cannot import name 'recover_signer'
```

The hostile suite subsequently reproduced and repaired malformed recovery-point
handling.

```text
python -m pytest -q -p no:cacheprovider tests/unit/test_attestation.py tests/unit/test_attestation_signing.py tests/integration/test_bridge_fixture.py
95 passed

python -m pytest -q -p no:cacheprovider
281 passed
```

Compiled Python-to-Solidity interoperability was established by GBL commit
`252d195` and remains passing against the provider-scoped quorum repair in GBL
commit `132a187`:

```text
forge test --ffi --match-path test/CanonicalBridge.t.sol -vv
5 passed
```

Negative coverage includes full replacement, r/s bit changes, invalid v,
truncation, appended bytes, zero r, zero s, high-s, wrong provider, wrong chain,
wrong contract, wrong name/version, field/root tampering, expiry, and integer
type/range failures.

## Public vector

`tests/fixtures/risk_attestation_v1_vector.json` contains only public values:
typed fields, domain separator, struct hash, digest, public key, 65-byte
signature, and recovered address. Tests recompute all hashes, recover the
provider, and independently call direct ECDSA verification with the committed
public key. The compiled canonical bridge accepts the Python-generated encoding
and signature against the deployed adapter domain. No private key is stored.

## Boundary and limitations

- Python schema/hash/signing/recovery and compiled interoperability have focused
  independent evidence.
- The vector is proven Solidity-compatible within the local compiled
  `CanonicalBridgeTest` scope.
- This report does not declare Task 7B GO, production readiness, or overall
  portfolio readiness.
