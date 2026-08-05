# 06 — Master Implementation Plan (FinVEST Redesign)

**Date:** 2026-08-06
**Status:** PLANNING — milestone-based, not time-boxed. Preregistration before
headline evaluation (Phase 1).

---

## Dependency graph

```
Phase 1 (governance + repo)
  ├─ finvest/ namespace + experiments/ + artifacts/
  ├─ PREREGISTRATION.md (freeze before any headline eval)
  └─ A0 integrity gates (leakage auditor, manifests)

Phase 2 (FinVEST-Bench) ── depends on Phase 1
  ├─ benchmark adapters (FinanceBench full, GRI-QA, SEC, ESEF)
  ├─ requirement-graph schema + gold schema
  ├─ paired conditions (FULL, OUTDATED, WRONG_PERIOD, ...)
  ├─ 5-level splitter + sealed dynamic test
  ├─ annotation tooling + agreement stats
  └─ leakage auditor (exact/fuzzy/semantic/issuer/template)

Phase 3 (document intelligence) ── depends on Phase 2 data
  └─ PDF/HTML/XBRL/visual normalization → EvidenceUnit

Phase 4 (requirement graph) ── depends on Phase 3
  └─ 3 parsers + graph-quality eval

Phase 5 (hierarchical retrieval) ── depends on Phase 3
  └─ doc router → page → region → fact; full-corpus + baselines

Phase 6 (candidate evidence graph) ── depends on 5
  └─ nodes + typed edges + provenance

Phase 7 (set selection) ── depends on 4, 5, 6
  └─ B1-B6 baselines + P1 VISTA-Fin learned selector

Phase 8 (numerical) ── depends on 5, 7
  └─ end-to-end table→row→cell→formula→execution

Phase 9 (temporal+version) ── depends on 5, 6, 7
  └─ joint source/valid/version constraint

Phase 10 (adversarial verification) ── depends on 7, 8, 9
  └─ 1,000+ cases, 15 error types, verifier comparison

Phase 11 (leak-free calibration) ── depends on 7, 9
  └─ inference-time features only; nested folds; conformal under exchangeability

Phase 12 (robustness) ── depends on 7, 8
  └─ paired perturbations + clustered CIs

Phase 13 (transfer) ── depends on 7, 2
  └─ FinVEST→external + external→FinVEST

Phase 14 (human study) ── depends on 7, 9, 10
  └─ interface (A/B/C), protocol, mixed-effects analysis

Phase 15 (EcoQuant integration) ── depends on 7-11
  └─ evidence package → attestation; architecture demo

Phase 16 (statistics) ── cross-cutting
Phase 17 (acceptance gates) ── cross-cutting
Phase 18 (reproducibility) ── cross-cutting
Phase 19 (paper) ── depends on 2-15
```

## Milestones (each commits separately)

| M | Deliverable | Acceptance |
|---|---|---|
| M1 | Governance + repo scaffold + A0 | leakage auditor runs; finvest/ namespace; preregistration frozen |
| M2 | FinVEST-Bench schema + first 200 cases | schema validates; agreement α ≥ 0.75 on core labels; no leakage |
| M3 | Document intelligence + requirement parsers | evidence units parse; graph-quality metrics reported |
| M4 | Full-corpus retrieval + baselines | doc/page recall tables; oracle gap quantified |
| M5 | Set selection (B1-B6 + P1) | set metrics vs baselines; ablations |
| M6 | Numerical + temporal/version end-to-end | joint-constraint results; adversarial verification 1,000 cases |
| M7 | Leak-free calibration + robustness + transfer | AUROC etc. leak-free; paired robustness; transfer tables |
| M8 | Human study (run by researcher) | protocol + interface ready; results when human data collected |
| M9 | EcoQuant integration + paper | paper tables auto-generated; acceptance gates pass |

## Branch / commit strategy

- `main` stays stable (pilot results preserved).
- New branch `redesign/finvest-bench` for Phase 1-2 scaffold.
- One branch per milestone after that; merge to `main` when milestone gates pass.
- Invalidated/oracle results stay in `artifacts/archive/`; never deleted.

## First milestone (M1) exact files

```
docs/redesign/                     (this set, 00-07)
docs/redesign/PREREGISTRATION.md   (freeze hypotheses/metrics/splits)
docs/audits/E5_GOLD_LEAKAGE_AUDIT.md (done)
finvest/__init__.py                (namespace scaffold)
finvest/benchmark/__init__.py
finvest/benchmark/schemas.py       (gold schema: case, requirement graph, evidence item)
finvest/benchmark/splitters.py     (5-level isolation)
finvest/benchmark/leakage_audit.py (exact/fuzzy/issuer/template detectors)
artifacts/archive/invalidated/e5_gold_leakage/  (done)
tests/research/test_no_gold_in_features.py      (done)
```

## Data/model assets: available vs missing

| Asset | Status |
|---|---|
| SEC XBRL companyfacts (6 co) | AVAILABLE (cache) |
| FinanceBench sample (150q) | AVAILABLE (cache); full 10-Ks MISSING |
| GRI-QA (266q) | AVAILABLE (cache) |
| dense all-MiniLM-L6-v2 | AVAILABLE (cache) |
| BGE-M3 | MISSING (downloadable) |
| ColPali | MISSING (GPU/vision assets) |
| EU ESEF reports | MISSING (license check needed) |
| FinMRAGBench/FinRAGBench-V/FinChain | MISSING (verify access/license) |
| Cross-encoder reranker | MISSING (blocked earlier; re-evaluate) |
