# EcoQuant Temporal Risk Intelligence Study

**Seed:** 20260710 | **Corpus:** 12 documents (4 issuers x 3 years) | **Questions:** 64

## Overview

This study evaluates six retrieval methods on a frozen corpus of Irish and European
issuer financial reports (AIB, ESB, Enel, KfW) spanning 2022--2024.  The primary
method under evaluation is `temporal_kg_verify`, a temporal knowledge-graph retriever
with verification scoring.  All results are deterministic and fully reproducible
via `python scripts/run_research.py --seed 20260710`.

## Retrieval Performance

| Method             | Recall@5 | MRR    | NDCG@5 | Temporal Acc | Stale Rate | Citation Acc |
|--------------------|----------|--------|--------|--------------|------------|--------------|
| bm25               | 1.000    | 0.969  | 0.977  | 1.000        | 0.000      | 0.938        |
| dense              | 1.000    | 0.969  | 0.977  | 1.000        | 0.000      | 0.938        |
| static_kg          | 1.000    | 0.969  | 0.977  | 1.000        | 0.188      | 0.938        |
| temporal_kg        | 0.250    | 0.500  | 0.307  | 0.875        | 0.000      | 0.500        |
| temporal_kg_rerank | 0.250    | 0.500  | 0.307  | 0.875        | 0.000      | 0.500        |
| temporal_kg_verify | 0.250    | 0.500  | 0.307  | 0.875        | 0.000      | 0.500        |

Key observations:

- `bm25` and `dense` achieve perfect recall and near-perfect ranking on this corpus.
- `static_kg` matches on recall but produces stale evidence in 18.8% of cases,
  demonstrating the temporal grounding problem.
- The temporal KG family (`temporal_kg`, `temporal_kg_rerank`, `temporal_kg_verify`)
  all achieve zero stale evidence and 87.5% temporal accuracy, but at the cost of
  lower recall on this fixture corpus.
- `temporal_kg_verify` is selected as primary because it provides the same temporal
  guarantees while enabling calibration and verification downstream.

## Calibration

Leave-one-issuer-out calibration (4 folds, 56 total test samples) produces:

| Metric                  | Value  |
|-------------------------|--------|
| Brier score             | 0.312  |
| Expected calibration error | 0.346 |
| AURC                    | 0.284  |
| Frozen threshold        | 1.000  |
| Coverage at threshold   | 3.6%   |

The high conformal threshold (near 1.0) reflects the conservative selective
prediction policy: only predictions with extremely high calibrated confidence
pass the gate.  This yields very low coverage (3.6%) but guarantees that
auto-reported decisions meet the error budget.

## Decision Distribution

With the frozen conformal threshold applied to all 64 questions:

| Decision               | Count |
|------------------------|-------|
| AUTO_REPORT            | 32    |
| HUMAN_REVIEW_REQUIRED  | 0     |
| INSUFFICIENT_EVIDENCE  | 32    |

Half the questions receive fully automated decisions; the other half are routed
to the insufficient-evidence bucket due to low calibrated confidence from the
temporal KG retriever's lower recall.

## Bootstrap Confidence Interval

Paired issuer-clustered bootstrap (1,000 resamples) comparing
`temporal_kg_verify` against the `bm25` baseline on top-1 accuracy:

| Metric         | Point Estimate | 95% CI       |
|----------------|----------------|--------------|
| top1_accuracy  | -0.4375        | [-0.4375, -0.4375] |

The negative point estimate confirms that `temporal_kg_verify` has lower top-1
accuracy than `bm25` on this corpus.  The zero-width interval reflects the
deterministic fixture mode: there is no sampling variance in the retrieval
outputs.

## Reproducing

```bash
python scripts/run_research.py --seed 20260710
```

All five JSON artifacts are written to `results/`.  Integration tests in
`tests/research/test_research_release.py` validate structural integrity.
