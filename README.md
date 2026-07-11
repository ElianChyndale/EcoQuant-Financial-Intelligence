# EcoQuant Financial Intelligence

Temporal knowledge-graph retrieval, calibrated uncertainty estimation, and
selective decision gating for financial issuer analysis.

## Quick Start

```bash
# Install
pip install -e .

# Run the full research pipeline
python scripts/run_research.py --seed 20260710

# Run tests
python -m pytest tests/ -v
```

## Repository Structure

```
src/ecoquant/
  retrieval/       # BM25, dense, KG, reranker, and verification retrievers
  evidence_graph/  # Temporal evidence graph with issuer/document nodes
  uncertainty/     # Calibration, conformal prediction, decision gating
  valuation/       # Policy and sensitivity analysis
  attestation/     # EIP-712 attestations and Merkle proofs

research/
  questions/       # Frozen benchmark questions (JSONL)
  labels/          # Gold labels
  sources/         # Source documents

scripts/
  run_research.py  # One-command reproducible research pipeline
  fetch_public_reports.py

tests/
  research/        # Research integration and calibration tests
  unit/            # Unit tests
  integration/     # Integration tests
  fixtures/        # Test fixtures

results/           # JSON artifacts from run_research.py
```

## Research

### Study Summary

The temporal risk intelligence study evaluates six retrieval methods on a frozen
corpus of 12 financial reports from four issuers (AIB, ESB, Enel, KfW) spanning
2022--2024, across 64 benchmark questions.

**Methods evaluated:**
`bm25`, `dense`, `static_kg`, `temporal_kg`, `temporal_kg_rerank`, `temporal_kg_verify`

**Primary method:** `temporal_kg_verify` -- a temporal knowledge-graph retriever
with verification scoring, selected for its zero stale-evidence rate and
compatibility with downstream calibration.

See `results/report.md` for the full analysis.

### Reproducing the Study

```bash
python scripts/run_research.py --seed 20260710
```

This produces five JSON artifacts in `results/`:

| File                    | Contents                                        |
|-------------------------|-------------------------------------------------|
| `study_manifest.json`   | Run parameters (seed, corpus size, methods)     |
| `retrieval_metrics.json`| Per-method retrieval scores across all questions|
| `calibration_result.json`| Leave-one-issuer-out calibration output        |
| `decision_summary.json` | Decision gating counts and conformal threshold  |
| `bootstrap_intervals.json`| Paired bootstrap confidence intervals          |

### Key Metrics

**Retrieval (temporal_kg_verify):**
- Recall@5: 0.250, MRR: 0.500, NDCG@5: 0.307
- Temporal accuracy: 87.5%, Stale evidence rate: 0.0%

**Calibration (4-fold, 56 samples):**
- Brier score: 0.312, ECE: 0.346, AURC: 0.284
- Frozen threshold: ~1.0 (conservative selective policy)

**Decisions (64 questions):**
- AUTO_REPORT: 32, HUMAN_REVIEW_REQUIRED: 0, INSUFFICIENT_EVIDENCE: 32

**Bootstrap (temporal_kg_verify vs bm25):**
- top1_accuracy point estimate: -0.4375 (95% CI: [-0.4375, -0.4375])

### Validating Results

Integration tests verify structural integrity of all result files:

```bash
python -m pytest tests/research/test_research_release.py -v
```

## License

See [LICENSE](LICENSE).
