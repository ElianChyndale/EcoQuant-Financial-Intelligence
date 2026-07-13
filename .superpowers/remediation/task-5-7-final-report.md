# Tasks 5-7 Final Remediation Report

**Date:** 2026-07-11
**Status:** PARTIALLY SUPERSEDED — no current GO; see SOL-4A repair below

## Task 5: Comparable Retrieval Methods and Evaluation

### Authoritative Requirements
- Six registered retrieval methods with shared top_k=5
- Genuine BM25, dense, KG, reranker, verifier backends
- Production backends must fail clearly on model load failure
- No gold data in retrieval
- Evaluator-only edges blocked

### Models / Agents Used
- Implementation: Main agent
- Review: Fresh retrieval methodology reviewer (read-only)

### Status: INTERNALLY FIXED — FRESH REVIEW REQUIRED; PRODUCTION EXECUTION EXTERNALLY BLOCKED

### Files Changed
- `src/ecoquant/retrieval/bm25.py` — Genuine rank-bm25 implementation
- `src/ecoquant/retrieval/dense.py` — Sentence-transformers with strict failure
- `src/ecoquant/retrieval/reranker.py` — Cross-encoder with strict failure
- `src/ecoquant/retrieval/kg.py` — Production metadata
- `src/ecoquant/retrieval/verifier.py` — Production metadata
- `src/ecoquant/retrieval/fixture.py` — Deterministic test backends
- `src/ecoquant/retrieval/base.py` — Mode support
- `tests/integration/test_production_backends.py` — Production backend tests

### Commits
- `f95b22b` — fix: complete production retrieval backends
- `bb31804` — fix: address independent reviewer findings (retrieval fixes)
- `7cc3280` — fix: enforce reproducible retrieval benchmark identity (incomplete boundary)
- `4d9f04e` — fix: enforce reproducible retrieval benchmark identity (SOL-4A repair)

### Current Focused Tests
- 77 Task 5/temporal-graph/production-backend tests passed
- 2 successful real-model integration tests skipped with explicit external-blocker reasons
- No full suite was run; that gate belongs to SOL-4B

### Independent Review
- The earlier GO verdict is superseded by SOL-4A.
- Fresh independent review of `4d9f04e` is required.

### Claims Now Safe
- The exact six-method final boundary is implemented and rejects unverified backends
- KG candidates are graph-derived and ranked without a full issuer-corpus scan
- Page/block citation metrics use an immutable evidence catalog
- Production mode fails clearly on missing models
- No gold data in retrieval
- Evaluator-only edges blocked

### Claims Still Unsafe
- Actual retrieval performance claims (requires real corpus and models)
- Successful production dense or reranker execution
- Final Task 8 release integration before SOL-4B

---

## Task 6: Calibration, Conformal Abstention, and Decision Gating

### Authoritative Requirements
- No gold leakage in features
- Nested issuer isolation
- Real Platt scaling
- Correct conformal direction
- Non-finite input rejection
- Split manifests

### Models / Agents Used
- Implementation: Main agent
- Review: Fresh statistical methods reviewer (read-only)

### Status: GO

### Files Changed
- `src/ecoquant/uncertainty/calibration.py` — Real Platt scaling with gradient descent
- `src/ecoquant/uncertainty/decision.py` — Non-finite rejection
- `scripts/run_research.py` — Gold leakage removed, calibrators applied, full manifests
- `tests/research/test_calibration_protocol.py` — Adversarial tests

### Commits
- `ea97389` — fix: implement leakage-free calibrated selective decisions
- `bb31804` — fix: address independent reviewer findings (calibration fixes)

### Green Tests
- 41 calibration protocol tests
- 9 decision gate tests

### Independent Review
- Reviewer: Fresh statistical methods reviewer
- Verdict: GO (after fix round)
- Key fixes:
  - Non-finite rejection in decide()
  - Gold leakage removed from evidence_sufficiency
  - Fitted calibrators applied in decision pipeline
  - Full split manifests in output

### Claims Now Safe
- No gold leakage in calibration features
- Nested issuer isolation with split manifests
- Real Platt scaling from training data
- Non-finite values cannot produce AUTO_REPORT

### Claims Still Unsafe
- Actual calibration performance (requires real retrieval results)

---

## Task 7: Valuation and Risk Attestation

### Authoritative Requirements
- Actual bond repricing with duration/convexity
- Genuine Ethereum Keccak (not NIST SHA-3)
- Correct EIP-712 typehash widths
- Cross-language test vectors

### Models / Agents Used
- Implementation: Main agent
- Financial review: Fresh financial modelling reviewer (read-only)
- Cryptography review: Fresh cryptography reviewer (read-only)

### Status: GO

### Files Changed
- `src/ecoquant/valuation/bond_pricing.py` — Bond pricing with duration/convexity
- `src/ecoquant/valuation/sensitivity.py` — Added units, base_spread_bps, adjusted_spread_bps
- `src/ecoquant/attestation/eip712.py` — Genuine Keccak, correct Solidity widths
- `tests/unit/test_attestation.py` — Cross-language vectors, bond pricing tests

### Commits
- `6bced74` — fix: align Python and Solidity risk attestations
- `bb31804` — fix: address independent reviewer findings (EIP-712 fixes)

### Green Tests
- 49 attestation and bond pricing tests
- Finite-difference verification passes

### Independent Review
- Financial reviewer: GO (bond pricing correct)
- Cryptography reviewer: GO (after typehash fix)
- Key fixes:
  - EIP-712 typehash uses correct Solidity widths (uint16, uint64, uint8)
  - SensitivityScenario includes units, base_spread_bps, adjusted_spread_bps

### Claims Now Safe
- Bond pricing is financially correct (verified against manual computation)
- Duration and convexity match finite-difference verification
- Ethereum Keccak used (not NIST SHA-3)
- EIP-712 typehash matches Solidity exactly

### Claims Still Unsafe
- Full Python-to-Solidity interoperability (requires GBL Task 12/14)
