# EcoQuant Financial Intelligence — FinVEST

Evidence-grounded financial question answering (FinVEST) with temporal,
version, and numerical verification plus calibrated, selective abstention.

**Current status (2026-08-07):** a small solo-provisional annotation pilot
(20 cases) and a pilot harness that flags its own gold-derived leakage. These
are **NOT paper-headline results**. See [RESEARCH_STATUS.md](RESEARCH_STATUS.md)
and [docs/redesign/00_CURRENT_STATE_AUDIT.md](docs/redesign/00_CURRENT_STATE_AUDIT.md)
for the live, honest status.

## Quick Start

```bash
# 1. Install dependencies
pip install -e .

# 2. Run the research pipeline (fixture mode for offline environments)
python scripts/run_research.py --mode fixture --seed 20260710

# 3. Run tests
python -m pytest tests/ -v
```

## Research Question

> Can an evidence-grounded financial QA system retrieve the correct evidence
> from an independent, leak-free SEC corpus, select a minimal sufficient
> evidence set, verify it temporally / version-wise / numerically, and
> abstain (rather than guess) when evidence is insufficient — such that its
> answers are verifiable and its abstention behavior is calibrated?

## Current Research Programme (E-series)

The active research programme is tracked in
[_research_program/planning/EXPERIMENT_REGISTRY.yaml](../_research_program/planning/EXPERIMENT_REGISTRY.yaml)
and the claim-evidence matrix in
[_research_program/planning/CLAIM_EVIDENCE_MATRIX.md](../_research_program/planning/CLAIM_EVIDENCE_MATRIX.md).
E0–E8 cover benchmark integrity, retrieval, table/numerical reasoning,
temporal reasoning, verification, calibration, human review, and system
integration. See [docs/redesign/00_CURRENT_STATE_AUDIT.md](docs/redesign/00_CURRENT_STATE_AUDIT.md)
for the per-experiment audit status.

## Repository Structure

```
src/ecoquant/       # Core research engine (retrieval, calibration, attestation)
finvest/            # FinVEST benchmark, retrieval, verification, set-selection
  benchmark/        #   Schemas, conditions, splitters, leakage audit, builders
  retrieval/        #   Full-corpus BM25/dense retrieval, metrics
  verification/     #   Temporal/version, numerical, adversarial verification
  set_selection/    #   Risk-controlled evidence-set selectors (S1–S4)
  calibration/      #   Leak-free calibration and selective prediction
human_review/       # Solo-provisional annotation protocol (day1)
experiments/        # E-series and pilot experiment harnesses
research/           # Questions, labels, sources, cache, results
scripts/            # One-command research pipeline + CLI entry points
tests/              # Research, unit, integration, and finvest tests
```

## Evidence → Label → Verify → Public Claim Pipeline

```text
SEC companyfacts / full 10-K
        ↓  (leak-free corpus — no gold rows)
Retrieval R1 BM25 / R2 dense / R3 RRF / R4 concept
        ↓  top-K candidates
Set selection S1 top-k / S2 greedy / S3 beam / S4 oracle
        ↓  minimal evidence set
Verification V1 temporal / V2 numerical / V3 joint
        ↓
ANSWER / REVIEW / ABSTAIN
        ↓
Experiment record → evidence dossier → portfolio / application
```

The annotation layer is human-driven (solo-provisional; human labels are
separate from machine-derived fields) and lives under `human_review/day1/`.
Evidence packages are versioned and hashed.

## Honest Status

Every claim in this README carries one evidence status:

```text
| Status | Meaning |
| --- | --- |
| **implemented** | Code exists and is exercised by tests; no research claim implied |
| **harness-validated** | A pilot harness runs it end-to-end, but the harness itself is known to be leaky/limited |
| **solo-provisional** | A single human annotator labeled it; not yet externally reviewed or gold |
| **experimentally supported** | Measured on a leak-free experiment with a defined protocol |
| **invalidated** | A previous result was retracted (e.g. gold-feature leakage); do not repeat |
```

Current state:

- 20 solo-provisional human annotations (16 ANSWER / 3 REVIEW / 1 ABSTAIN);
  17 `SOLO_PROVISIONAL`, 3 `NEEDS_EXTERNAL_REVIEW` — **solo-provisional**.
- The A10 harness
  ([experiments/a10_integration/minimal_experiments.py](experiments/a10_integration/minimal_experiments.py))
  runs on the annotated cases and **explicitly flags gold-derived leakage**:
  the pilot's retrieval pool is each case's own evidence rows, so set-selection
  numbers are not meaningful retrieval results — **harness-validated only**.
- The A10 V-layer now invokes the real joint temporal/version and numerical
  verifiers (`joint_verifier_invoked: true`); its pass rates are honest
  verification rates, not a year-equality check — **harness-validated**.
- Evidence packages are **frozen** per case
  ([human_review/evidence_packages/](human_review/evidence_packages/)) with a
  full-package SHA-256 + `PACKAGE_MANIFEST.json`, so a second annotator reads
  byte-for-byte the same page — **implemented**.
- A **gold-blind (leak-free) SEC corpus** is built and frozen
  ([research/corpus/](research/corpus/)): 170k+ facts from companyfacts only,
  `SOURCE_MANIFEST` + `CORPUS_MANIFEST` + `SPLIT_MANIFEST`, zero gold tokens in
  corpus records. The builder survives all gold/annotation files being removed
  — **implemented**.
- The A11 two-stage experiment
  ([experiments/a11_retrieval/run.py](experiments/a11_retrieval/run.py))
  retrieves from the leak-free corpus (R1 BM25 / R2 dense / R3 RRF / R4
  concept-temporal), selects evidence sets (S1–S4), and verifies (V1–V3),
  reporting the three layers separately — **harness-validated**.
- Challenge-case generation
  ([finvest/benchmark/builders/challenge_cases.py](finvest/benchmark/builders/challenge_cases.py))
  produces wrong-period / future-source / amendment / scale-sign / duplicate /
  insufficient variants so the verifier's REJECTION (not just acceptance) is
  tested — **implemented**.
- Tool adapters under [integrations/](integrations/) wire in
  `financial-ai-contracts`, `financial-systems-verification-kit`, and
  `paper-reproduction-lab` (pinned in `INTEGRATION_LOCK.json`) — **implemented**.

## Documentation

- [Research Status](RESEARCH_STATUS.md) — live result classification
- [Redesign audit](docs/redesign/00_CURRENT_STATE_AUDIT.md) — E0–E8 audit
- [Architecture](docs/architecture.md)
- [Dataset Card](docs/dataset_card.md)
- [Model Card](docs/model_card.md)
- [Evaluation Protocol](docs/evaluation.md)
- [Limitations](docs/limitations.md)
- [Failure Cases](docs/failure_cases.md)

## Historical / Invalidated Results

The following claims are **NOT** current results. They come from an earlier
"green-bond temporal RAG" research thread that was invalidated by gold-derived
leakage and oracle-conditioned evaluation. They are retained only as history.

- **"BM25 and dense achieve 1.000 Recall@5 with 0% stale evidence"** —
  `ORACLE_CONDITION` (evaluated against gold-page corpora).
- **"Temporal KG methods have 0.250 Recall@5"** — `ORACLE_CONDITION`.
- **"Calibrated abstention at 3.6% coverage (threshold 0.913)"** —
  `INVALIDATED`; the calibration feature leaked gold relevance
  ([E5_GOLD_LEAKAGE_AUDIT.md](docs/audits/E5_GOLD_LEAKAGE_AUDIT.md)).
- **"Green Bond Lending trust boundary / EIP-712 RiskAttestationV1"** —
  superseded by the FinVEST evidence-verification framing.

See [RESEARCH_STATUS.md](RESEARCH_STATUS.md) for the result-classification
table and [docs/redesign/01_INVALIDATED_CLAIMS.md](docs/redesign/01_INVALIDATED_CLAIMS.md).

## License

See [LICENSE](LICENSE).
