# E5 Gold-Feature Leakage Audit

**Status:** CONFIRMED — E5 headline result INVALIDATED
**Audit date:** 2026-08-06
**Auditor:** Claude Code (independent read of committed code)
**Result file:** `research/results/e5_calibration_summary.json` (archived)

---

## 1. Summary

The E5 calibration experiment's headline metrics (AUROC 0.923, ECE 0.054,
Brier 0.085, coverage-at-90%-precision 0.006) are **invalidated** because the
`evidence_coverage` feature is computed from the gold relevant-evidence set,
which is not available at inference time.

## 2. Evidence

File: `src/ecoquant/research/calibration_eval/features.py`
Function: `build_features_from_retrieval(results_by_method, relevant_by_question)`

```python
# relevant_by_question is the GOLD relevance mapping (from EvaluatorGold).
relevant = relevant_by_question[qid]

# Feature 5 (evidence_coverage) = fraction of GOLD evidence retrieved.
coverage = len(retrieved_ids & relevant) / len(relevant) if relevant else 0.0
features.append(UncertaintyFeatures(..., evidence_coverage=coverage))

# Correctness label also derived from the SAME gold set.
labels.append(bool(top1.evidence_id in relevant))
```

File: `scripts/run_e5_calibration.py`

```python
# Gold relevance is passed directly into the feature builder.
features, labels = build_features_from_retrieval(company_results, company_questions)
# where company_questions = gold.relevant_evidence filtered per company
```

## 3. Why this is leakage

- `evidence_coverage` requires knowing which evidence IDs are relevant (the
  gold set). At inference time on a new question, this set is unknown.
- The Platt calibrator was trained on features including this gold-derived
  signal, so its probability estimates are inflated: the model learns "how
  much gold did I retrieve" — a perfect predictor that cannot exist in
  production.
- The correctness label uses the same gold set. Labels for *evaluation* are
  legitimate; using the same gold set to *construct a feature* is not.

## 4. Impact on headline claims

| Claim (E5 report §4-5) | Status |
|---|---|
| AUROC 0.923 for correctness ranking | **INVALIDATED_GOLD_FEATURE_LEAKAGE** |
| ECE 0.054, Brier 0.085 | **INVALIDATED_GOLD_FEATURE_LEAKAGE** |
| Coverage 0.6% at 90% precision | **INVALIDATED_GOLD_FEATURE_LEAKAGE** |
| "retrieval margin separates correct/wrong by 3x" | margin feature itself is leak-free; the *separation statistic* is descriptive, but it was reported as evidence for calibration quality → **de-emphasise; margin-only re-run required** |
| "calibration certifies precision, does not create it" | conclusion may survive a leak-free re-run, but the supporting numbers are invalidated |

## 4b. Quantified impact (leak-free rerun, 2026-08-06)

After removing the gold-derived feature, the same pipeline was re-run with
leak-free features only (margin, agreement, extraction confidence, temporal
validity; coverage placeholder = 0.0):

| Metric | Leaky (invalidated) | Leak-free rerun | Δ |
|---|---|---|---|
| AUROC | 0.923 | **0.719** | −0.204 |
| ECE | 0.054 | 0.055 | +0.001 |
| Brier | 0.085 | **0.126** | +0.041 |
| Coverage at 90% precision | 0.006 | 0.004 | −0.002 |

The gold-derived `evidence_coverage` feature inflated AUROC by ~0.20 — a
material distortion. The leak-free AUROC 0.719 is the honest baseline for
Phase 11 (full leak-free feature set).

## 5. Action taken

1. `research/results/e5_calibration_summary.json` archived to
   `artifacts/archive/invalidated/e5_gold_leakage/` with a status manifest.
2. This audit document created.
3. Regression test added (`tests/research/test_no_gold_in_features.py`) that
   fails if any non-oracle feature builder reads gold relevance/evidence/answer.
4. E5 report updated to mark the headline as INVALIDATED.
5. All active claim surfaces (README, claim-evidence matrix, application
   materials) must remove the E5 headline numbers until a leak-free re-run
   exists.

## 6. What a valid re-run requires

A leak-free feature set (inference-time available only):

- top1-top2 margin,
- cross-retriever agreement,
- reranker score (when available),
- requirement-prediction coverage (predicted, not gold),
- temporal-verifier flags,
- conflict flags,
- execution-verifier outputs,
- candidate-set entropy.

No feature may be a function of gold relevance, gold pages, gold answers, gold
programs, or gold labels.
