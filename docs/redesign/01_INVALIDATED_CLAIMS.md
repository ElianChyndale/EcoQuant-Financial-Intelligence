# 01 — Invalidated Claims (FinVEST Redesign Phase 0)

**Date:** 2026-08-06
**Status:** FINAL — these claims are removed from all active surfaces.

---

## 1. E5 calibration headline (INVALIDATED_GOLD_FEATURE_LEAKAGE)

| Claim | Original value | Status |
|---|---|---|
| AUROC for correctness | 0.923 | **INVALIDATED_GOLD_FEATURE_LEAKAGE** |
| ECE | 0.054 | **INVALIDATED_GOLD_FEATURE_LEAKAGE** |
| Brier | 0.085 | **INVALIDATED_GOLD_FEATURE_LEAKAGE** |
| Coverage at 90% precision | 0.006 | **INVALIDATED_GOLD_FEATURE_LEAKAGE** |

**Reason:** `evidence_coverage` feature = `len(retrieved & gold_relevant) /
len(gold_relevant)` — gold-derived, not inference-time available. Leak-free
rerun: AUROC 0.719, ECE 0.055, Brier 0.126, coverage@90 0.004 (see
`docs/audits/E5_GOLD_LEAKAGE_AUDIT.md` §4b).

**Leak-free replacement values (valid to report):**
- AUROC 0.719 (leak-free, margin/agreement/confidence/temporal features only)
- This is the honest baseline for Phase 11.

## 2. Claims to remove from active surfaces

The following surfaces must NOT contain the invalidated E5 numbers:

- [ ] `research/reports/E5_CALIBRATION_SELECTIVE.md` §4-5 (mark INVALIDATED; keep
      leak-free rerun as the replacement)
- [ ] `research/reports/RESEARCH_PROGRAMME_OVERVIEW.md` §4/§5 (E5 row)
- [ ] `_research_program/planning/CLAIM_EVIDENCE_MATRIX.md` (E5 rows)
- [ ] `academic-application-generator` generated materials (any PS/CV quoting
      AUROC 0.923)
- [ ] README / any public Markdown

## 3. Other claims requiring re-labeling

| Claim | Old status | New status |
|---|---|---|
| E1 "dense 0.563 R@5 on FinanceBench" | headline | **PILOT_ORACLE_CONDITION** (gold-page corpus; full-doc gap unmeasured) |
| E2 "94% tolerance accuracy" | headline | **PILOT_ORACLE_CONDITION** (gold row/col cells) |
| E3 "source filter eliminates future info" | headline | **PILOT** (small sample; not joint-constrained) |
| E4 "false-pass 0.0" | headline | **PILOT_STRESS_TEST** (30 injected cases; needs 1,000+ adversarial set) |
| E8 "citation 0→1.0" | headline | **ARCHITECTURE_DEMO** (6 cases) |

## 4. Rule going forward

No headline claim may be published unless:
1. its feature construction is leak-free (guard test passes),
2. its corpus is full-document (not gold-filtered),
3. its evaluation unit is question/issuer/document-family (not per-retriever
   output),
4. it is labelled PILOT / ORACLE / DEMO when not the headline result.
