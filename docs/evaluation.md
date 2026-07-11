# Evaluation Protocol

## Retrieval Metrics

- **Recall@5:** Fraction of relevant evidence in top-5 results
- **Hit@5:** Binary: any relevant evidence in top-5
- **MRR:** Mean reciprocal rank of first relevant result
- **nDCG@5:** Normalized discounted cumulative gain
- **Temporal accuracy:** First result valid for requested time
- **Stale evidence rate:** Results with valid_time > cutoff
- **Contradiction F1:** F1 for contradiction detection
- **Citation accuracy:** First result in citation evidence set

## Calibration Metrics

- **Brier score:** Mean squared error of calibrated probabilities
- **ECE:** Expected calibration error (10 equal-width bins)
- **AURC:** Area under risk-coverage curve
- **Coverage at threshold:** Fraction accepted by frozen threshold

## Decision Metrics

- **AUTO_REPORT:** Calibrated + conformal + sufficient evidence
- **HUMAN_REVIEW_REQUIRED:** Evidence present but below gate
- **INSUFFICIENT_EVIDENCE:** Invalid extraction or missing evidence

## Statistical Validity

- **Bootstrap:** Issuer-clustered paired bootstrap (1000 samples, seed 20260710)
- **Folds:** Leave-one-issuer-out (4 folds)
- **Threshold:** Frozen on calibration data before test evaluation

## Reproducibility

- Fixed seed (20260710) for all random operations
- Deterministic corpus records
- Pinned model revisions
- Machine-readable result artifacts
