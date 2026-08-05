# PREREGISTRATION — FinVEST: Version-Aware, Executable and Sufficient Evidence Sets

**Frozen:** 2026-08-06
**Status:** PREREGISTERED — no headline evaluation may begin until this file is
complete and reviewed. Do not change these definitions after observing final
test results.

---

## 1. Central hypothesis

> For financial questions over a full document universe, a system that retrieves
> a **minimum sufficient evidence set** (complete, time-valid, version-consistent,
> executable, minimal) and routes ANSWER / REVIEW / ABSTAIN on set-level
> sufficiency will achieve lower false-support and higher all-required-evidence
> recall than systems that rank single passages.

## 2. Primary hypotheses (frozen)

| ID | Hypothesis | Direction |
|---|---|---|
| H1 | VISTA-Fin set selector ≥ strong baselines on All-Required-Evidence Recall at equal set size | positive |
| H2 | VISTA-Fin set selector lowers False-Support Rate vs top-k / SURE-style baselines at similar coverage | positive |
| H3 | Joint temporal+version constraint lowers future+expired+superseded rates vs separate filters | positive |
| H4 | Executable verification reduces unsupported derived answers (false-support) | positive |
| H5 | Leak-free calibrated confidence enables selective control (risk-coverage) better than uncalibrated scores | positive |
| H6 | Full-document retrieval is materially harder than gold-page retrieval (oracle gap) | positive (descriptive) |
| H7 | Evidence packages (Condition C) improve human review vs answer-only / top-k pages | positive (human study) |

## 3. Primary metrics (frozen)

Per experiment (A1-A9), the primary metric is **frozen before evaluation**:

| Exp | Primary metric |
|---|---|
| A1 full retrieval | All-Required-Evidence Recall@k (document+page level) |
| A2 set selection | All-Required-Evidence Recall + Set Exact Match (acceptable-set) |
| A3 numerical | End-to-end numerical accuracy (tolerance 1%) |
| A4 temporal | Joint future+expired+superseded rate (composite, defined) |
| A5 verification | False-Support Rate (primary); False-Reject Rate (secondary) |
| A6 selective | Coverage at fixed risk (1% / 5% / 10%) |
| A7 robustness | Paired performance drop (mean + CI) |
| A8 transfer | Per-dataset metric (no single merged average) |
| A9 human | Unsafe acceptance rate (primary); review time (secondary) |

Statistical unit: **question**, clustered by issuer and document family.
Clustered bootstrap CIs; paired permutation tests; Holm correction.

## 4. Data splits (frozen)

- Level 1 issuer isolation; Level 2 document-family isolation; Level 3 temporal
  isolation; Level 4 question-template isolation; Level 5 evidence-family
  isolation.
- Test-A IID issuer-held-out; Test-B chronological; Test-C cross-jurisdiction
  (US→EU); Test-D sealed dynamic (labels not in workspace).

## 5. Threshold / selection rules (frozen)

- Thresholds selected ONLY on inner calibration folds (never outer test).
- No test-set tuning, feature normalization on test, or error-driven code
  modification after viewing test results.
- At least 3 seeds (5 for headline method); report mean/SD/CI.

## 6. Baseline set (frozen)

BM25, TF-IDF, LSA, dense bi-encoder, BGE-M3 (sparse/dense/multi-vector),
hybrid RRF, cross-encoder reranker, ColPali visual (if assets), long-context,
document-contextualized, SURE-RAG-style aggregation. No baseline may be
replaced by a weaker proxy.

## 7. Ablations (frozen)

Remove-one-component for: requirement graph, hierarchical retrieval,
candidate evidence graph, set selector, temporal/version verifier, executable
verifier, calibration, counterfactual dropout.

## 8. Human study endpoints (frozen)

24-30 reviewers; 240 stratified cases; within-subject crossover A/B/C;
Latin-square counterbalancing; ≥3 independent decisions per case; mixed-effects
model with reviewer/question/issuer random effects. Power analysis from pilot
BEFORE final data collection.

## 9. Exclusion rules (frozen)

- Cases with unresolvable annotation disagreement (post-adjudication) excluded
  with documented count.
- Private/commercial data never mixed with public benchmark.
- Any case where raw evidence is unavailable (license/technical) excluded with
  documented reason.

## 10. Go/No-Go (frozen)

- Benchmark: core-label Krippendorff α ≥ 0.75; entity/period/numeric agreement
  ≥ 0.90; no leakage; ≥80% cases pass adjudication.
- Method: ≥2 of {All-Required-Evidence Recall gain, False-Support reduction,
  temporal/version gain, human unsafe-acceptance reduction} with CIs.
- If the method does not clearly beat baselines: report the negative result and
  position as benchmark/resource paper. No test tuning to force significance.
