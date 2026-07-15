# SOL-4B Implementation Matrix

**Authority:** coordination contract `docs/remediation/SOL4B_INTEGRATION_CONTRACT.md`

**Scope:** Task 8 integration only; no frozen Task 5, 6, 7A, or 7B contract changes.

**Status:** Internally implemented; production release remains externally blocked. No Task 5 GO or final production claim.

| Clause | Classification | Production symbol | RED/focused evidence | Status | Result | Commit | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Call `compare_retrievers(methods, query, top_k=5, final_benchmark=True)` | REQUIRED_BY_CONTRACT | `_run_production_retrieval`, `_run_production_retrieval_with_provenance` | `test_production_calls_exact_final_task5_boundary` | implemented | green | `899aa4e` | Model execution blocked after entering the final boundary |
| Production corpus comes only from `adapt_evidence_spans(...)` | REQUIRED_BY_CONTRACT | `load_production_inputs` | deterministic authoritative-adaptation and existing handcrafted-final rejection tests | implemented | green | `899aa4e` | none |
| Approved cached source bytes are hash-checked before normalized input | MECHANICAL | `load_production_inputs` | `test_changed_source_and_normalized_bytes_change_recorded_hashes`, source-hash mismatch test | implemented | green | `899aa4e` | Cache index only locates approved manifest rows, bytes, source dates, assets, and normalized JSON; it changes no upstream schema |
| Normalized bytes and document/evidence/issuer/asset/page/block/time/structured-value identity survive adaptation | REQUIRED_BY_CONTRACT | `load_production_inputs`, `adapt_evidence_spans` | `test_identical_production_adaptation_is_deterministic_and_authoritative` | implemented | green | `899aa4e` | none |
| Malformed required source or normalized fields fail machine-readably | REQUIRED_BY_CONTRACT | `_strict_json_bytes`, `load_production_inputs` | malformed normalized-document and source-hash tests | implemented | green | `899aa4e` | none |
| Methods come only from `all_retrievers(..., mode="production")` and are exactly the six IDs | REQUIRED_BY_CONTRACT | both production retrieval functions | exact-boundary test plus frozen SOL-4A adversaries | implemented | green | `899aa4e` | none |
| Queries carry explicit shared `valid_at` and `source_cutoff` | REQUIRED_BY_CONTRACT | `_load_queries`, `_validate_production_arguments` | temporal-cutoff CLI tests | implemented | green | `899aa4e` | none |
| Final fingerprints, trusted instances, complete dependencies, and matching per-query receipts are consumed | REQUIRED_BY_CONTRACT | `_run_production_retrieval_with_provenance` | frozen SOL-4A identity/dependency/receipt adversaries | implemented | green | `899aa4e` | Genuine dense/reranker receipts unavailable |
| Boundary failures occur before artifact emission | REQUIRED_BY_CONTRACT | `run`, `_write_production_release` | no-fallback/missing-input tests plus frozen SOL-4A boundary adversaries | implemented | green | `899aa4e` | none |
| Fixture/exploratory/unavailable backends and inference failures cannot complete production | REQUIRED_BY_CONTRACT | `run`, final Task 5 comparison | production attempt: exit 2, `production_retrieval_blocked`, no output directory | implemented | expected blocker | `899aa4e` | Dense weights and reranker snapshot/revision unavailable |
| Fixture output cannot claim production/final | REQUIRED_BY_CONTRACT | `_run_fixture_compatibility`, `_fixture_manifest`, `_fixture_attestation` | `test_fixture_output_cannot_claim_production` | implemented | green | `899aa4e` | none |
| Production requires source cache, question set, cutoffs, fitted Task 6 state, signing configuration, and dependency lock | REQUIRED_BY_CONTRACT | CLI validation, `_require_fitted_task6_state`, `_require_release_dependency_lock` | mode-gate and fitted-state tests | implemented | green | `899aa4e` | Exact lock unresolved |
| Page/block evidence catalog reaches citation evaluation | REQUIRED_BY_CONTRACT | `_compute_production_metrics` | `test_production_forwards_evidence_location_catalog` | implemented | green | `899aa4e` | none |
| Frozen Task 6 normalization, converged calibrator, coefficients, conformal/decision thresholds, split manifests, and decision policy are consumed | REQUIRED_BY_CONTRACT | `_fit_production_task6`, `_require_fitted_task6_state` | fixture fitted-state and unfitted-state tests; frozen Task 6 suites | implemented | green | `899aa4e` | none |
| Decision precedence remains insufficient, human review, auto report | REQUIRED_BY_CONTRACT | frozen `decide` via Task 6 gating | `tests/unit/test_decision_gate.py`, decision summary integration | unchanged/consumed | green | `899aa4e` | none |
| Explicit-date Task 7A valuation emits clean/dirty price, accrued interest, durations, convexity, and complete provenance | REQUIRED_BY_CONTRACT | `_fixture_valuation_rows`, `_production_valuation_rows` | explicit-date release test plus frozen valuation suites | implemented | green | `899aa4e` | Documented unsupported bond features remain |
| Canonical RiskAttestationV1 uses sorted evidence, explicit model/domain/provider, external production key, 65-byte recovery, and provider equality | REQUIRED_BY_CONTRACT | `_fixture_attestation`, `_production_attestation`, `SigningConfiguration` | canonical fixture and external-key production-envelope tests plus frozen signing suites | implemented | green | `899aa4e` | Production signing config intentionally external |
| Exactly seven isolated, non-empty, stable, UTF-8, finite principal artifacts; stale output rejected | REQUIRED_BY_CONTRACT | staging writers and `_PRINCIPAL_ARTIFACTS` | artifact, finite-value, completion-status, and stale-output tests | implemented | green | `research: validate reproducible Task 8 artifacts` | none |
| Manifest records repository/run/sources/retrieval/calibration/valuation/attestation/limitations and exact six artifact byte hashes without self-hash | REQUIRED_BY_CONTRACT | `_fixture_manifest`, `_write_production_release` | `test_manifest_contract_and_exact_non_manifest_byte_hashes` | implemented | green | `research: validate reproducible Task 8 artifacts` | Dependency-lock blocker recorded |
| Fixture reruns freeze run ID, timestamp, nonce, key derivation, and semantic ordering | REQUIRED_BY_CONTRACT | fixture finalizer and writers | two isolated CLI releases compared byte-for-byte | implemented | seven identical artifact hashes | `research: validate reproducible Task 8 artifacts` | none |
| Production blockers are machine-readable, non-zero, no-fallback, and emit no final artifacts | REQUIRED_BY_CONTRACT | `Task8Error`, `main`, `run` | single production attempt | implemented | exit 2; output absent | `899aa4e` | Four external blockers reported |
| Task 8 never downloads model assets without authorization | REQUIRED_BY_CONTRACT | `_offline_model_loading` | `test_production_model_loading_is_forced_offline` | implemented | green | `899aa4e` | Local snapshots still incomplete |
| Private signing key is never committed, serialized, or logged | REQUIRED_BY_CONTRACT | signing configuration and envelope serializers | no-secret artifact test and external-key envelope test | implemented | green | `899aa4e` | none |

## Verification

- Focused SOL-4B and frozen adjacent suites on the final code state: `495 passed, 2 skipped`.
- Full EcoQuant suite, run exactly once: `511 passed, 2 skipped`. The later narrow offline guard was verified by its focused regression test rather than rerunning the full suite.
- Fixture rerun: all seven artifact byte hashes and lengths matched.
- Production attempt: exit `2`, code `production_retrieval_blocked`, `fixture_fallback=false`, artifact directory absent.

## Frozen Limitation

Extraction confidence remains a bounded retrieval-score proxy pending an approved upstream extraction-confidence contract. Production dense weights, a verified immutable reranker revision and usable snapshot, successful real dense/reranker inference, and the exact dependency lock remain external blockers rather than successful production verification.
