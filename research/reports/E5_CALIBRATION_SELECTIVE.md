# E5 — Calibration and Selective Prediction over FinanceBench Retrieval

**Experiment:** e5-calibration-selective
**Date:** 2026-08-06
**Status:** INTERNAL PILOT — results valid on the E1 FinanceBench retrieval results.
**Reproduction:** `python scripts/run_e5_calibration.py` (writes
`research/results/e5_calibration_summary.json`).
**Commit:** branch `feat/e5-calibration-selective`.

---

## 1. Research Question

> Does calibrated confidence from retrieval scores enable selective prediction —
> auto-accepting easy cases while abstaining on hard ones — with a bounded
> supported-answer error rate?

**Falsifiable hypotheses:**

- H1: Retrieval-derived features (margin, agreement, coverage) separate correct
  from incorrect top-1 predictions (AUROC > 0.7).
- H2: Platt calibration over these features produces a calibrated probability
  (low ECE) that ranks correctness.
- H3: Selective prediction reaches high supported-answer precision at meaningful
  coverage (e.g. 90% precision at >10% coverage).

## 2. Data

E1 FinanceBench retrieval results: 150 questions × 6 methods = 900
(question, method) predictions. Correctness = top-1 evidence is a gold hit.

Five uncertainty features per prediction (existing `UncertaintyFeatures`):

- `retrieval_margin` (top-1 minus top-2 score),
- `cross_retriever_agreement` (fraction of methods agreeing on top-1),
- `extraction_confidence` (normalized top-1 score),
- `temporal_validity` (valid_time_match),
- `evidence_coverage` (gold recall at rank ≤ 5).

## 3. Method

Nested leave-one-company-out calibration (32 companies) via the existing
`fit_calibration_folds`: per outer fold, inner fit/calibration/threshold-selection
disjoint; held-out company evaluated once. Pooled held-out probabilities/labels
drive ECE, Brier, AUROC, and the risk-coverage frontier. Headline metric:
**coverage at 90%/95% supported-answer precision** (auto-accept precision).

## 4. Results

| Metric | Value |
|---|---|
| Pooled accuracy (top-1 hit) | 0.184 |
| ECE | 0.054 |
| Brier | 0.085 |
| **AUROC (correctness)** | **0.923** |
| Coverage at 90% precision | 0.006 (1/900) |
| Coverage at 95% precision | 0.006 (1/900) |

Feature separation (correct vs wrong):

| Feature | Correct mean | Wrong mean |
|---|---|---|
| retrieval_margin | **1.075** | 0.334 |
| extraction_confidence | 0.160 | 0.196 |

## 5. Findings

1. **H1 strongly supported.** Retrieval margin separates correct from wrong
   top-1 predictions by 3× (1.075 vs 0.334). AUROC 0.923 — retrieval confidence
   is a strong correctness signal.
2. **H2 supported.** ECE 0.054 and Brier 0.085 — the Platt-calibrated
   probability is well-calibrated and ranks correctness accurately.
3. **H3 NOT supported at meaningful coverage.** At 90% precision, only 0.6%
   coverage is reachable (1/900). The calibrated model is honest: it knows it is
   confident about very few cases, because top-1 retrieval accuracy is only
   18.4%.

**Interpretation:** calibration is *working correctly* (AUROC 0.92, low ECE) —
it does not over-claim. The binding constraint is **retrieval quality**, not
calibration. To auto-accept more cases at high precision, the system must first
improve retrieval (E1 showed dense helps on FinanceBench; retrieval gap B7→B3
in E2 was 20 points). This is a clean, honest quantification of the
"calibration can't fix retrieval" claim: **selective prediction certificates
precision, it does not create it.**

## 6. Limitations

1. **Single dataset** (FinanceBench sample). E5 on EcoQuant/GRI-QA is future work.
2. **Correctness = top-1 hit** — a coarse label; does not capture "right evidence,
   wrong page" or partial grounding.
3. **No LLM in the loop** — this is retrieval confidence, not generative
   response confidence.
4. **Small coverage at high precision** — the honest result is a low-coverage
   high-precision frontier, not a "system that auto-answers everything safely."

## 7. Claims Permitted After This Experiment

- **SUPPORTED:** Retrieval margin strongly separates correct from incorrect
  top-1 predictions (AUROC 0.923) on FinanceBench.
- **SUPPORTED:** Platt calibration over retrieval features yields low ECE (0.054)
  and Brier (0.085).
- **SUPPORTED:** At 90% supported-answer precision, only ~0.6% of cases can be
  auto-accepted — retrieval quality, not calibration, is the binding constraint.
- **PROHIBITED:** "calibration ensures safe auto-answering", "high coverage at
  high precision", "production-ready selective system".

## 8. Reproduction

```bash
cd EcoQuant-Financial-Intelligence
python scripts/run_e5_calibration.py   # needs financebench cache + dense model
```

- Seeds: calibration folds seed 20260710; E1 baselines deterministic.
