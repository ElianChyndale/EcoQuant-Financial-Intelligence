# EcoQuant Tasks 5–8 Principal Repair Plan

**Date:** 2026-07-12  
**Baseline:** `d7d86adcf2c33017fa1e060cfe0f679bd301a097`  
**Status:** Implementation plan; no task is declared GO  
**Order:** Task 6 → Task 7B → Task 7A → Task 5 → Task 8 → independent reviews

## Frozen baseline

- Repository: `ecoquant-financial-intelligence`, branch `main`, clean status.
- Remotes/tags: none.
- Baseline suite: 239 tests collected; 239 passed.
- Tracked results are the older five-file fixture release, not the authoritative seven-file release.
- Local dense snapshot: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.
- Reranker cache contains no usable snapshot; the configured revision is a negative-cache placeholder.
- Available crypto libraries include `ecdsa 0.19.2` and `pycryptodome 3.23.0`.

## Finding-to-repair map

| Task | Production symbol/finding | RED test | Repair contract | Expected files | Commit | Review gate |
| --- | --- | --- | --- | --- | --- | --- |
| 6 | `fit_calibration_folds`: nonconformity ignores observed label | Correct and incorrect examples with equal probability produce different correctness nonconformity scores | Define `1-p` for correct and `p` for incorrect; calibrate only on the inner calibration issuer | uncertainty calibration/conformal tests | `fix: implement valid nested conformal calibration` | Fresh statistical review |
| 6 | Inner roles reuse calibration data for decision-threshold selection | Per-fold role sets are disjoint; outer mutations leave all frozen state unchanged | Deterministic fit/calibration/threshold issuer roles; reject insufficient issuer count | calibration module/tests | same | Fresh statistical review |
| 6 | Unconverged or degenerate Platt fit enters final execution | Forced low iteration/degenerate labels block final policy construction | Record objective/failure reason and require fitted, finite, converged, nondegenerate state for final use | calibration, runner, tests | same | Fresh statistical review |
| 6 | Feature agreement denominator varies; evidence coverage is score-scale dependent | Missing one method reduces agreement over fixed six; score rescaling does not change coverage | Fixed six-method denominator; coverage is verified, temporally valid, graph-supported top-five proportion | runner/features/tests | same | Fresh statistical review |
| 6 | `decide` ignores learned fold threshold and temporal validity | Two fold policies with different thresholds produce different decisions | Immutable `DecisionPolicy` carries probability, evidence and temporal gates; fold policy is consumed | decision, runner, tests | same | Fresh statistical review |
| 6 | Non-evaluable values can become non-portable JSON | Strict JSON serialization rejects no valid result | Portable `null` plus evaluability/reason metadata | metrics/runner/tests | same | Fresh statistical review |
| 7B | Integer schema accepts floats/bools | Every integer field rejects `1.0` and `True` | Exact `type(value) is int` and Solidity-width bounds | models/tests | `fix: implement recoverable risk attestation signatures` | Fresh crypto review |
| 7B | `verify_signature` trusts metadata and accepts tampering | Replace/flip/truncate/extend signature; all fail | Canonical 65-byte `r||s||v`, low-s, recovery, provider comparison, bound runtime domain | signing/tests/vector fixture | same | Fresh crypto review |
| 7B | Fixed vectors are Python self-consistency only | Fixed expected domain/struct/digest/signature/recovered address | Public vector generated from deterministic test key and verified through an independent recovery path; no private key committed | tests/fixtures/report | same | Fresh crypto review; compiled Solidity remains pending Tasks 12/14 |
| 7A | Fractional maturity is truncated | Fractional maturity and explicit maturity date produce the same schedule | Replace `maturity_years` schedule inference with explicit maturity date while retaining a validated compatibility constructor | bond pricing/tests | `fix: implement coherent settlement-aware bond valuation` | Fresh financial review |
| 7A | Day-count/discounting hybrid and full stub coupon | Closed-form par/zero/premium fixtures plus short-stub coupon fixture | Actual/Actual ICMA coupon-period fractions; backward schedule; nominal periodic discounting with consistent period fractions | bond pricing/tests/docs | same | Fresh financial review |
| 7A | Invalid schedules/discount factors are not rejected | Leap/month-end/impossible stub and `1+y/m<=0` cases fail | Deterministic month-end schedule and strict financial input validation | pricing/tests | same | Fresh financial review |
| 7A | Evidence ID falls back to risk-factor text | Supported adjustment without evidence cannot change spread | Actual evidence IDs required; explicit unsupported/no-adjustment result | sensitivity/tests | same | Fresh financial review |
| 5 | Shared corpus validation checks only length | Equal-length different corpora fail final comparison; reorder preserves identity | Canonical SHA-256 fingerprint over sorted retriever-visible schema fields | retrieval base/tests | `fix: enforce reproducible retrieval benchmark identity` | Fresh retrieval review |
| 5 | Task 8 bypasses final comparison | Production runner test observes `top_k=5` and final validation | Exact six IDs, production metadata, verified revisions, shared query/cutoffs/fingerprint | base/runner/tests | same | Fresh retrieval review |
| 5 | Placeholder model revisions/minimum dependency ranges | Placeholder/missing revisions fail final validation | Record verified immutable snapshots and exact research-critical package versions | model manifest/pyproject/tests | same | Fresh retrieval review; successful model loading is an execution gate |
| 5 | Empty contradiction case emits literal NaN | Strict JSON contains no NaN/Infinity | Structured non-evaluable metric value with reason | evaluation/runner/tests | same | Fresh retrieval review |
| 5 | Docs call custom graph NetworkX | Claim scan rejects NetworkX graph wording | Describe `TemporalEvidenceGraph` truthfully | docs | same | Fresh retrieval review |
| 8 | Production path uses `_CORPUS` | Production mode without normalized input fails; fixture corpus cannot enter production | Explicit `--mode`; production consumes normalized documents and EvidenceSpanV1; fixtures isolated | runner/fixture module/tests | `research: rebuild production EcoQuant release pipeline` | Fresh release review |
| 8 | Valuation and attestation are not called | Release integration test spies real repaired boundaries and validates public-only signed output | Execute Task 7A and 7B after a frozen Task 6 policy | runner/tests | same | Fresh release review |
| 8 | Wrong artifact names/types and stale release tests | Exact seven-file contract fails before implementation | Three substantive CSVs, two more CSVs, two strict JSON files as specified; no legacy substitutes | runner/results tests | same | Fresh release review |
| 8 | Manifest hashes canonical objects rather than written bytes | Recomputed byte hashes equal manifest entries | Write/close artifacts, hash exact bytes, then write non-self-referential manifest | runner/tests | same | Fresh release review |
| 8 | Fixture-only CI and unsupported public claims | CI/job and claim-safety tests fail on fixture-as-production wording | Separate offline/statistical/crypto/valuation/release jobs and manual production gate; artifact-linked qualified docs | CI/docs/paper | same | Fresh release review |

## Commit and stop discipline

Each phase begins with an observed RED failure, changes only its declared scope,
runs its focused suites plus prior repaired suites, inspects the staged diff, and
creates the listed correction commit. Production execution is reported as
externally blocked—not passed—if normalized documents or verified model snapshots
are unavailable. Compiled Solidity interoperability remains pending GBL Tasks
12/14 and is never represented as Python completion.

## Final evidence

After all implementable phases, write `docs/remediation/SOL_TASKS_5_8_FINAL_REPORT.md`,
run the full suite and two isolated fixture reproductions, and request separate
read-only statistical, cryptographic, financial, retrieval, release, and final
integration reviews. The implementation worker does not issue final GO.
