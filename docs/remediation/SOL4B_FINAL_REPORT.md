# SOL-4B Task 8 Integration Report

**SOL-4B:** PARTIAL_EXTERNAL_BLOCKER

**Internal status:** Task 8 integration is implemented and contract-focused verification is green. This is not a Task 5 GO or final EcoQuant GO.

**Production source path:** approved external `source_manifest.csv` plus cache index, hash-matched source bytes, `normalized_document_v1`, `EvidenceSpanV1`, sealed `AuthoritativeCorpus`, and corpus schema v3 records.

**Task 5 integration:** exact six factory-created production retrievers; explicit shared valid/source cutoffs; `top_k=5`; `final_benchmark=True`; factory identities, dependency chains, and per-query execution receipts captured for the manifest.

**Task 6 integration:** nested issuer calibration, fitted normalization, finite converged coefficients, conformal and decision thresholds, frozen decision policy, risk-coverage output, and strict decision precedence are consumed without changing statistical definitions.

**Task 7A integration:** explicit settlement/maturity dates, backward EOM schedule, Actual/Actual ICMA, nominal coupon-frequency compounding, clean/dirty price, accrued interest, Macaulay/modified duration, convexity, and evidence/rule provenance.

**Task 7B integration:** canonical RiskAttestationV1, sorted evidence-root construction, explicit model/domain/provider, external production key, deterministic fixture key derivation, 65-byte recoverable signature, and provider recovery verification.

**Artifacts:** exactly seven principal artifacts; legacy substitute files removed; isolated staging, stable ordering/columns, strict finite JSON, non-empty outputs, and stale-output rejection.

**Manifest:** `task8-manifest.v1` covers repository, run, sources, retrieval, calibration, valuation, attestation, limitations, and exact byte hashes/sizes for the six non-manifest artifacts; no circular self-hash.

**Fixture rerun:** two isolated seed-`20260710` executions matched byte-for-byte for all seven artifacts.

**Focused tests:** expanded SOL-4B/frozen-adjacent suite reported 495 passed and 2 known production-load skips on the final code state.

**Full EcoQuant:** 511 passed, 2 skipped, run exactly once. The narrow no-download guard was added afterward and verified directly without rerunning the full suite.

**Production attempt:** one attempt exited 2 with `production_retrieval_blocked`, `fixture_fallback=false`, and no artifact directory.

**External blockers:** dense snapshot lacks executable weights; reranker lacks a verified immutable revision and usable snapshot; genuine dense/reranker inference is unavailable; exact release dependency lock is unresolved.

**Commits:** integration `899aa4e`; validation commit `research: validate reproducible Task 8 artifacts`.

**Fresh review required:** yes — contract-limited EcoQuant review; no final GO.

## Preserved Limitations

- Extraction confidence remains a bounded retrieval-score proxy pending an approved upstream extraction-confidence contract.
- No business-day adjustment, ex-coupon support, floating-rate bonds, amortizing bonds, defaulted-cash-flow model, or unsupported complex stubs.
- Fixture artifacts are a deterministic local demonstration and cannot satisfy the production release gate.
