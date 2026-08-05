# 00 — Current State Audit (FinVEST Redesign Phase 0)

**Date:** 2026-08-06
**Status:** READ-ONLY AUDIT COMPLETE — no production code modified by this document.
**Scope:** E0-E8 pilots in `EcoQuant-Financial-Intelligence` (branch `main`, 39 commits ahead of origin).

---

## 1. What exists (verified against source + tests)

| Asset | Location | Status |
|---|---|---|
| E0 dataset adapters (EcoQuant corpus, FinanceBench) | `src/ecoquant/research/datasets/` | IMPLEMENTED + TESTED |
| E0 integrity validator | `scripts/run_e0_validate.py` | PASS (leakage tests, gold separation) |
| E1 retrieval baselines (BM25/TFIDF/LSA/dense/RRF/long-context) | `src/ecoquant/research/retrieval_eval/` | IMPLEMENTED + TESTED |
| E1 results (FinanceBench 150q, dense 0.563 R@5) | `research/results/e1_retrieval_summary.json` | **PILOT_ORACLE_CONDITION** (gold-page corpus) |
| E2 table reasoning (GRI-QA 266q, calc separation) | `src/ecoquant/research/table_eval/` | IMPLEMENTED + TESTED |
| E2 94% tolerance result | `research/results/e2_table_summary.json` | **PILOT_ORACLE_CONDITION** (gold row/col cells) |
| E3 temporal (SEC XBRL, source/valid filters) | `src/ecoquant/research/temporal_eval/` | IMPLEMENTED + TESTED |
| E3 contradiction F1 +76% | `research/results/e3_temporal_summary.json` | PILOT (small sample; joint constraints missing) |
| E4 verifier (false-pass 0.0) | `src/ecoquant/research/verification_eval/` | IMPLEMENTED + TESTED |
| E5 calibration | `src/ecoquant/research/calibration_eval/` | **INVALIDATED_GOLD_FEATURE_LEAKAGE** (fixed, rerun pending) |
| E7 commercial analysis | `src/ecoquant/research/commercial_eval/` | IMPLEMENTED + TESTED |
| E8 integration comparison | `src/ecoquant/research/integration_eval/` | IMPLEMENTED + TESTED (6-case demo) |
| 8 experiment reports | `research/reports/` | Present; several contain now-invalidated numbers |
| Claim-evidence matrix | `_research_program/planning/CLAIM_EVIDENCE_MATRIX.md` | Must be updated for invalidations |
| Full test suite | `tests/` | 624 passed, 2 skipped (pre-invalidation) |

## 2. Confirmed defects

1. **E5 gold-feature leakage (CONFIRMED).** `evidence_coverage` feature =
   `len(retrieved & gold_relevant) / len(gold_relevant)` — gold-derived,
   unavailable at inference. Headline AUROC 0.923 invalidated. See
   `docs/audits/E5_GOLD_LEAKAGE_AUDIT.md`. **Fixed** (leak-free features +
   explicit evaluation-only labels); rerun in progress.

2. **E1 oracle-conditioned corpus.** FinanceBench retrieval ran on a corpus of
   the 168 *gold evidence pages only* — not the full documents. Headline
   numbers are an oracle upper bound; the full-corpus gap is unmeasured.

3. **E2 oracle-conditioned cells.** The 94% tolerance result uses gold
   row/column indices — it is a calculation upper bound, not end-to-end.

4. **E3 disjoint constraints.** B5's contradiction dedup raised future-rate to
   0.585 — constraints were optimized separately, not jointly.

5. **E8 tiny demo.** 6 cases; structural demonstration only.

## 3. Reusable assets (genuinely sound)

- Dataset adapters + gold-separation discipline (E0) — **keep, extend**.
- Leakage tests + integrity validator (E0) — **keep, extend** to five-level
  isolation + leakage auditor.
- SEC XBRL adapter + fiscal-year handling (E3/E7) — **keep**; real-world data.
- Deterministic calculators + unit/year normalization (E2) — **keep** as
  executable-verification core.
- Multi-layer verifier (E4) — **keep**; needs 1,000+ adversarial cases.
- Decision gate (`decide`, conformal, RiskAttestationV1) — **keep**; the
  routing + attestation boundary is sound.
- Concept-resolution layer (E7) — **keep**.

## 4. What the redesign must change

| Old assumption | Redesign requirement |
|---|---|
| Corpus = gold pages | Full-document corpus (A1) |
| Gold cells for calc | End-to-end table retrieval → cells (A3) |
| Separate temporal constraints | Joint temporal+version constraint (A4) |
| Gold-derived features | Leakage-free features only (A6) |
| 6-case integration | Architecture demo, not headline (A10) |
| Independent experiments | One task: minimum sufficient evidence sets |
