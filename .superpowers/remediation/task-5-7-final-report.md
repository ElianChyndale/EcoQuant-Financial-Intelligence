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

### Status: SOL-4A INTERNALLY CLOSED — INDEPENDENT CONTRACT REVIEW PASS; PRODUCTION EXECUTION EXTERNALLY BLOCKED

### Files Changed
- `src/ecoquant/retrieval/bm25.py` — Genuine rank-bm25 implementation
- `src/ecoquant/retrieval/dense.py` — Sentence-transformers with strict failure
- `src/ecoquant/retrieval/reranker.py` — Cross-encoder with strict failure
- `src/ecoquant/retrieval/kg.py` — Production metadata
- `src/ecoquant/retrieval/verifier.py` — Production metadata
- `src/ecoquant/retrieval/fixture.py` — Deterministic test backends
- `src/ecoquant/retrieval/base.py` — Mode support, exact typed canonical JSON
  corpus identity, immutable method-derived requirements, and final receipt validation
- `src/ecoquant/retrieval/corpus_adapter.py` — Sealed authoritative
  `EvidenceSpanV1` to schema-v3 retrieval corpus boundary
- `src/ecoquant/retrieval/production_factory.py` — Approved six-backend construction boundary
- `src/ecoquant/retrieval/provenance.py` — Factory instance identities, complete
  dependency chains, and run-scoped successful-execution receipts
- `tests/research/test_retrieval_methods.py` — Fingerprint collision and canonical
  encoding adversaries
- `tests/integration/test_production_backends.py` — Production backend metadata tests

### Commits
- `f95b22b` — fix: complete production retrieval backends
- `bb31804` — fix: address independent reviewer findings (retrieval fixes)
- `7cc3280` — fix: enforce reproducible retrieval benchmark identity (incomplete boundary)
- `4d9f04e` — fix: enforce reproducible retrieval benchmark identity (SOL-4A repair)
- `c132d78` — fix: canonicalize retrieval corpus identity (first correction)
- `f17c03f` — fix: close retrieval identity and metadata bypasses (second correction)
- `a421f71` — fix: bind retrieval corpus identity to normalized evidence (final identity architecture)
- `42d1f9d` — fix: bind production verification to executed backends (final provenance architecture)
- `99904d7` — docs: record final SOL-4A architectural repair
- Root coordination `b829cef` — docs: record SOL-4A final architectural repair

### Current Focused Tests
- 188 Task 5/adapter/provenance/temporal-graph/production-backend tests passed
- 2 successful real-model integration tests skipped with explicit external-blocker reasons
- No full suite was run; that gate belongs to SOL-4B

### Independent Review
- The independent SOL-4A review failed because delimiter-only fingerprint
  serialization allowed two distinct equal-length corpora to collide, and the
  metadata validator accepted a production-verified graph method with an empty
  backend identifier.
- The second independent review failed because binary-float coercion collapsed
  adjacent large integers, Decimal values had no exact contract, fingerprint-only
  NFKC/casefold collapsed retriever-visible text, and caller capability flags
  could suppress dense/reranker identity requirements.
- The second correction uses corpus schema v2 with exact stored text and tagged
  numeric values, and selects immutable production requirements only by canonical
  method ID. Caller capability flags must exactly match the selected method.
- The third independent review failed because document identity and the
  `EvidenceSpanV1` adapter were absent, NumPy float64 entered implicitly,
  fingerprint values were not strictly typed, composite provenance was
  incomplete, and final mode still trusted caller-created metadata and
  constructor-only model state.
- The final architectural correction freezes
  `docs/remediation/SOL4A_FINAL_ACCEPTANCE_CONTRACT.md`, maps authoritative
  evidence to schema-v3 records, rejects NumPy scalars, validates exact built-in
  lowercase SHA-256 strings, and accepts final results only from factory-created
  backend instances with matching run-scoped execution receipts.
- Fresh review is limited to the frozen final acceptance contract and commits
  `a421f71`, `42d1f9d`, and `99904d7`, with root coordination `b829cef`.
- The independent contract review returned **PASS**: all internally
  implementable frozen-contract clauses passed, no clause failed, and no
  authoritative-design contradiction was found. SOL-4A is internally closed.
  This does not claim successful final production execution or a Task 5
  production GO; the external blockers below remain unresolved.

### Frozen Corpus Identity V2
- `None` is `{"type":"null"}`.
- Arbitrary-precision integers are `{"type":"integer","value":"<base-10>"}`;
  booleans are rejected before the integer path.
- Finite `Decimal` values use type `decimal`, plain notation without exponent,
  no fractional trailing zeroes, preserved non-zero sign, and normalized signed
  zero `0`.
- Existing finite binary floats use type `binary_float` and exact `float.hex()`;
  NaN and infinities are rejected.
- Source numerical text uses type `source_text` and preserves the exact stored
  representation. Integer, Decimal, binary float, and source text remain distinct.
- The exact stored corpus text is encoded without fingerprint-only NFKC,
  case-folding, trimming, tokenization, or whitespace/punctuation rewriting.

### Frozen Final Architecture V3
- The sealed production adapter preserves source schema, evidence/document,
  issuer/asset, page/block, exact text, valid interval, source time, bounding
  box, hashes, provider, confidence, and named structured numerical identity.
- Handcrafted records remain fixture-capable but cannot enter the production
  factory or final mode.
- NumPy and unsupported third-party scalar values are rejected; supported
  built-in Python numbers retain the v2 exact policies.
- Final fingerprints must be exact built-in 64-character lowercase hexadecimal
  strings before constant-time comparison with independently recomputed hashes.
- Factory identities bind method, concrete backend type, instance/run IDs,
  adapter receipt, corpus fingerprint, actual package versions, model pins,
  graph/temporal contracts, reranker identity, and verifier identity.
- Successful receipts bind corpus, query, valid/source cutoffs, top-k,
  dependencies, output digest, method, instance, and run. Every invocation
  resets prior inference state; constructors and stale status cannot create a receipt.

### Claims Now Safe For Fresh Review
- The exact six-method final boundary is implemented and rejects unverified,
  empty, fixture, exploratory, placeholder, or method-incompatible backends
- Canonical corpus identity is structurally unambiguous, type-preserving, and
  independently testable at the serialized-byte boundary
- Production model and revision requirements cannot be weakened through
  caller-supplied capability flags
- Caller-created metadata, receipt-shaped values, copied provenance, and
  fabricated retrievers cannot satisfy final mode
- KG candidates are graph-derived and ranked without a full issuer-corpus scan
- Page/block citation metrics use an immutable evidence catalog
- Production mode fails clearly on missing models
- No gold data in retrieval
- Evaluator-only edges blocked

### Claims Still Unsafe
- Actual retrieval performance claims (requires real corpus and models)
- Successful production dense or reranker execution
- A final Task 5 production result while dense/reranker execution and the exact
  release dependency lock remain externally blocked
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
