# EcoQuant Financial Intelligence

Temporal knowledge-graph retrieval, calibrated uncertainty estimation, and
selective decision gating for financial issuer analysis.

## Quick Start

```bash
# 1. Install dependencies
pip install -e .

# 2. Run the research pipeline (fixture mode for offline environments)
python scripts/run_research.py --seed 20260710 --fixture

# 3. Run tests
python -m pytest tests/ -v
```

## Research Question

> Does temporal evidence-graph retrieval, combined with calibrated abstention,
> reduce stale or unsupported green-bond risk conclusions compared with vector
> and static-graph retrieval?

## Key Findings

- **Temporal filtering eliminates stale evidence:** 0% stale rate for temporal methods
- **Calibrated abstention:** Conservative policy with 4% coverage
- **Decision gate:** 50% AUTO_REPORT, 50% INSUFFICIENT_EVIDENCE

## Architecture

```text
PDF Manager → EvidenceSpanV1 → Temporal Graph → Retrieval → Calibration → Decision → Valuation → Attestation
```

See [docs/architecture.md](docs/architecture.md) for details.

## Repository Structure

```
src/ecoquant/
  retrieval/       # BM25, dense, KG, reranker, and verification retrievers
  evidence_graph/  # Temporal evidence graph with issuer/document nodes
  uncertainty/     # Calibration, conformal prediction, decision gating
  valuation/       # Bond pricing, policy, and sensitivity analysis
  attestation/     # EIP-712 attestations and Merkle proofs

research/
  questions/       # Frozen benchmark questions (JSONL)
  labels/          # Gold labels
  sources/         # Source documents
  results/         # JSON artifacts from run_research.py

scripts/
  run_research.py  # One-command reproducible research pipeline
  fetch_public_reports.py

tests/
  research/        # Research integration and calibration tests
  unit/            # Unit tests
  integration/     # Integration tests
```

## Documentation

- [Architecture](docs/architecture.md)
- [Dataset Card](docs/dataset_card.md)
- [Model Card](docs/model_card.md)
- [Evaluation Protocol](docs/evaluation.md)
- [Limitations](docs/limitations.md)
- [Failure Cases](docs/failure_cases.md)
- [Research Report](paper/report.md)

## Trust Boundary

EcoQuant produces recommendations but never executes financial actions:

- **EcoQuant owns:** Document extraction, retrieval, calibration, valuation sensitivity
- **GBL owns:** Identity, bonds, settlement, lending, liquidation
- **Interface:** Signed EIP-712 RiskAttestationV1

AI cannot directly move funds or trigger liquidation.

## License

See [LICENSE](LICENSE).
