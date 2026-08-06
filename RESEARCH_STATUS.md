# Research Status

**Date:** 2026-08-06
**Status legend:** ENGINEERING_COMPLETE · PILOT_VALIDATED · AWAITING_HUMAN_VALIDATION · UNTRAINED_SCAFFOLD · INVALIDATED · PLANNED

---

## Module status

| Module | Status | Notes |
|---|---|---|
| E5 old AUROC 0.923 | **INVALIDATED** | Gold-derived `evidence_coverage` feature; archived with manifest |
| E5 leak-free AUROC 0.719 | **PILOT_VALIDATED** | Rebuilt with inference-time features only; guard test enforced |
| E1/E2/E3/E4/E7/E8 pilot results | **PILOT_VALIDATED** (oracle-conditioned where noted) | E1 gold-page corpus, E2 gold cells — upper bounds, not headline |
| FinVEST SEC case builder (22 base cases) | **PILOT_VALIDATED** | Schema validates, tests pass; candidate labels need human verification |
| Paired conditions generator | **ENGINEERING_COMPLETE** | FULL/PARTIAL/OUTDATED/WRONG_PERIOD/CONFLICTING/DISTRACTOR/OCR |
| Full 10-K corpus (6 companies) | **ENGINEERING_COMPLETE** | Cache-only; 1.5-8.5MB per document; gitignored |
| Full-corpus retrieval (BM25 + dense) | **ENGINEERING_COMPLETE** | A1 metrics implemented; oracle gap to be quantified with gold |
| Requirement-graph parsers | **ENGINEERING_COMPLETE** (deterministic) / **UNTRAINED_SCAFFOLD** (LLM, trainable) | Deterministic parser tested; LLM needs API key; trainable needs data |
| Set selection (B1-B4) | **ENGINEERING_COMPLETE** | top-k, greedy cover, beam, ILP oracle |
| VISTA-Fin learned selector | **UNTRAINED_SCAFFOLD** | Interface + deterministic proxy; learned weights need training data |
| Joint temporal+version verifier | **ENGINEERING_COMPLETE** | Fixes E3 disjoint-constraint issue |
| Executable numerical verification | **ENGINEERING_COMPLETE** | Reuses E2 calculator; cell localization added |
| Adversarial verification benchmark | **ENGINEERING_COMPLETE** | Scales to 1,000+ cases; human-checked gold labels PLANNED |
| Leak-free calibration (A6) | **ENGINEERING_COMPLETE** | Metrics implemented; real-data run needs gold labels |
| Robustness perturbations (A7) | **ENGINEERING_COMPLETE** | 14 paired perturbations |
| Transfer reporting (A8) | **ENGINEERING_COMPLETE** | Per-dataset reporting, no merged average |
| Human study (A9) | **AWAITING_HUMAN_VALIDATION** | Protocol + interface ready; needs 24-30 human reviewers |
| 2,000-case benchmark | **PLANNED** | 22 base cases now; scale-up needs more companies + annotation |
| EcoQuant integration (A10) | **ENGINEERING_COMPLETE** | Evidence package + boundary enforced; architecture demo |
| Paper | **PLANNED** | Auto-tables generate; main.tex to write |

## Result classification

| Result | Classification |
|---|---|
| E5 AUROC 0.923 | INVALIDATED_GOLD_FEATURE_LEAKAGE |
| E5 leak-free AUROC 0.719 | PILOT_VALIDATED (margin/agreement/confidence/temporal only) |
| E1 dense > sparse (FinanceBench) | PILOT_ORACLE_CONDITION (gold-page corpus) |
| E2 94% tolerance | PILOT_ORACLE_CONDITION (gold cells) |
| E4 false-pass 0.000 | PILOT_STRESS_TEST (30 cases) |
| E8 citation 0→1.0 | ARCHITECTURE_DEMO (6 cases) |
