# 02 — Oracle-Conditioned Claims (FinVEST Redesign Phase 0)

**Date:** 2026-08-06
**Status:** PILOT_ORACLE_CONDITION — preserved for auditability, NOT headline.

These claims are valid as *upper bounds on specific components* but were
presented as if end-to-end. The redesign removes the oracle condition.

---

## E1: FinanceBench retrieval (gold-page corpus)

- **Claim:** dense R@5 0.563 > hybrid 0.511 > sparse 0.29-0.38.
- **Oracle condition:** the corpus was the **168 gold evidence pages only** —
  the retriever never had to find evidence inside full 10-K documents.
- **Valid use:** upper bound on page-level ranking given oracle filtering.
- **Invalid use:** "retrieval works on real financial documents."
- **Redesign:** A1 full-corpus retrieval; quantify the oracle gap.

## E2: GRI-QA calculation (gold cells)

- **Claim:** known-table deterministic calc 94% within 1%.
- **Oracle condition:** gold **row/column indices** were used to locate cells.
- **Valid use:** upper bound on the calculator + unit/year normalization.
- **Invalid use:** "end-to-end table QA."
- **Redesign:** A3 end-to-end (table retrieval → row/col → cells → formula →
  execution); 94% becomes the oracle calculation bound.

## E3: temporal filtering (small sample)

- **Claim:** source filter future-rate 0.339→0; valid filter expired 0.089→0.
- **Oracle-adjacent condition:** 234-question stratified sample; constraints
  optimized separately (B5 future-rate rose to 0.585 under joint pressure).
- **Redesign:** A4 joint temporal+version constraint; full question set.

## E4: verification (small stress test)

- **Claim:** false-pass 0.000.
- **Condition:** 30 injected unsupported cases (number-not-in-evidence).
- **Valid use:** stress test of the deterministic verifier.
- **Invalid use:** "verifier eliminates unsupported answers."
- **Redesign:** A5 1,000+ adversarial cases across 15 error types.

## E8: integration (6-case demo)

- **Claim:** citation 0→1.0, review routing 0→0.67.
- **Condition:** 6 demonstration questions.
- **Valid use:** architecture demonstration of the AI/non-AI boundary.
- **Invalid use:** "system replaces legacy."
- **Redesign:** A10 architecture demo only; headline evidence comes from
  A1-A9.
