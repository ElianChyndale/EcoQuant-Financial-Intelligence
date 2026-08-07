# E5 — Calibration and Selective Prediction over FinanceBench Retrieval

**Experiment:** e5-calibration-selective
**Date:** 2026-08-06
**Status:** HEADLINE **INVALIDATED** (gold-feature leakage); leak-free rerun
`PILOT_VALIDATED` — see [audit](docs/audits/E5_GOLD_LEAKAGE_AUDIT.md).
The original headline (AUROC 0.923, ECE 0.054, Brier 0.085) is **retracted**:
the `evidence_coverage` feature was computed from the gold relevant-evidence
set, which is unavailable at inference time.
**Current result (leak-free):** AUROC **0.719**, ECE **0.055**, Brier **0.126**,
coverage at 90% precision **0.004** (pooled accuracy 0.184). Small sample, pilot
only — **not a paper headline.**
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

> **Leak-free rerun (current).** The `evidence_coverage` feature is pinned to
> 0.0 (gold-derived coverage removed). Original gold-leaked numbers are
> archived and **must not be quoted**.

| Metric | Leak-free (current) | Original (INVALIDATED) |
|---|---|---|
| Pooled accuracy (top-1 hit) | 0.184 | 0.184 |
| ECE | **0.055** | 0.054 |
| Brier | **0.126** | 0.085 |
| **AUROC (correctness)** | **0.719** | **0.923** |
| Coverage at 90% precision | **0.004 (1/225)** | 0.006 (1/900) |
| Coverage at 95% precision | **0.004 (1/225)** | 0.006 (1/900) |

Feature separation (correct vs wrong, leak-free rerun):

| Feature | Correct mean | Wrong mean |
|---|---|---|
| retrieval_margin | 1.075 | 0.334 |
| extraction_confidence | 0.160 | 0.196 |

## 5. Findings

> **Validity caveat:** the pre-fix AUROC 0.923 / ECE 0.054 / Brier 0.085 are
> **INVALIDATED** by gold-feature leakage (`evidence_coverage` was a function of
> the gold relevant set). Only the leak-free rerun below is reportable.

1. **H1 supported at lower strength (leak-free).** Retrieval margin still
   separates correct from wrong top-1 predictions, but AUROC drops from the
   leaked 0.923 to **0.719** once the gold-derived coverage feature is removed —
   retrieval confidence is a *moderate* correctness signal, not a near-perfect
   one.
2. **H2 partially supported.** The leak-free rerun shows ECE 0.055 and Brier
   0.126 — calibration is intact but the probability ranks correctness less
   accurately than the (invalidated) leaked numbers suggested.
3. **H3 NOT supported at meaningful coverage.** At 90% precision, only 0.4%
   coverage is reachable (1/225). The calibrated model is honest: it is confident
   about very few cases, because top-1 retrieval accuracy is only 18.4%.

**Interpretation:** after removing the gold leak, calibration still *does not
create* precision — the binding constraint remains **retrieval quality**, not
calibration. To auto-accept more cases at high precision, the system must first
improve retrieval. This is the honest leak-free quantification of the
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
5. **Small sample** — 225 pooled leak-free predictions; pilot only, no headline
   claim.

## 7. Claims Permitted After This Experiment

- **PILOT_VALIDATED (leak-free):** After removing the gold-derived feature,
  retrieval margin separates correct from incorrect top-1 predictions with
  AUROC **0.719** (pilot; not a headline). Do **not** quote the original 0.923.
- **PILOT_VALIDATED (leak-free):** Platt calibration over leak-free features
  yields ECE 0.055 and Brier 0.126.
- **PILOT_VALIDATED (leak-free):** At 90% supported-answer precision, only ~0.4%
  of cases can be auto-accepted — retrieval quality, not calibration, is the
  binding constraint.
- **INVALIDATED (do not state):** "AUROC 0.923", "ECE 0.054", "Brier 0.085",
  "retrieval confidence reliably separates correct/incorrect".
- **PROHIBITED:** "calibration ensures safe auto-answering", "high coverage at
  high precision", "production-ready selective system".

## 8. Reproduction

```bash
cd EcoQuant-Financial-Intelligence
python scripts/run_e5_calibration.py   # needs financebench cache + dense model
```

- Seeds: calibration folds seed 20260710; E1 baselines deterministic.
