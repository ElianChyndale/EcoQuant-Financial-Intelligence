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
| Human study (A9) | **AWAITING_HUMAN_VALIDATION** | Protocol + interface ready; needs 24-30 human reviewers; day-1 single-reviewer pilot PREPARED (queues frozen, labels pending) — A9 NOT complete |
| FinVEST day-1 pilot **v0.1** (22 base cases) | **INVALIDATED_BENCHMARK_CONSTRUCTION** | Cross-concept amendment pairing; immutable artifact preserved read-only at `human_review/day1/v0.1/`; NOT human-validated. See `docs/human_workbench/V0_1_INVALIDATION.md` |
| FinVEST day-1 pilot **v0.2-draft** | **PARTIAL_REPAIR — SCIENTIFIC_AUDIT_INCOMPLETE** | Amendment identity repaired; canonical resolution + preflight in progress; **not** `READY_FOR_ANNOTATION`, `AUDIT COMPLETE`, or `PILOT VALIDATED`. Draft only at `human_review/day1/v0.2-draft/` |
| Paired / blind / interface (v0.1) | **INVALIDATED_ARTIFACTS** | v0.1 queue variants are invalidated alongside v0.1; future variants are v0.2-draft artifacts pending freeze |
| VISTA-Fin learned selector (day-1 pilot) | **INSUFFICIENT_DATA_FOR_TRAINING** | Gated runner ready (leave-one-issuer-out × 3 seeds, low-capacity logistic, inference-time features); 0 human labels → training skipped honestly; `PILOT_TRAINED_EXPLORATORY` after labels |
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
| Day-1 pilot v0.1 (22 base / 12 paired / 5 blind / 9 interface) | **INVALIDATED_BENCHMARK_CONSTRUCTION** — cross-concept amendment pairing; zero human labels existed; hashes preserved |
| Day-1 pilot v0.2 (21 base / 12 paired / 5 blind / 9 interface) | CANDIDATE_QUEUE_REBUILT — repaired; zero human labels; verification claims not made |
| VISTA_PILOT_V0_1 | INSUFFICIENT_DATA_FOR_TRAINING (0 human-verified labels; exploratory, not headline) |
