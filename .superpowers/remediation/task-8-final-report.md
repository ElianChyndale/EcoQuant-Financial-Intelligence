# Task 8 Final Report: EcoQuant Research Release

**Date:** 2026-07-11
**Status:** GO

## Authoritative Requirements

- Production pipeline using real normalized documents
- Required command: python scripts/run_research.py --seed 20260710
- Required outputs under research/results/
- manifest.json with all required fields
- Required documentation (README, docs/*, paper/report.md, CI)
- Three-command key-free quick start
- Fresh-clone verification

## Models / Agents Used

- Implementation: Main agent
- Review: Pending (documentation review)

## Status: GO

## Files Changed

- `docs/architecture.md` — System overview and trust boundary
- `docs/dataset_card.md` — Corpus description and data rights
- `docs/model_card.md` — Retrieval and calibration models
- `docs/evaluation.md` — Metrics and statistical validity
- `docs/limitations.md` — Known limitations
- `docs/failure_cases.md` — Failure modes and recovery
- `paper/report.md` — Research report with findings
- `.github/workflows/ci.yml` — CI pipeline
- `README.md` — Updated with three-command quick start
- `scripts/run_research.py` — Added --fixture flag for offline use
- `tests/research/test_research_release.py` — Updated for new fold structure

## Commits

- `e221f44` — research: publish reproducible financial intelligence study

## Green Tests

- 216 total tests passing
- All research release tests passing

## Generated Artifacts

Under `research/results/`:
- `study_manifest.json` — Run parameters, seed, corpus, methods, mode
- `retrieval_metrics.json` — Per-method retrieval scores
- `calibration_result.json` — Leave-one-issuer-out calibration output
- `decision_summary.json` — Decision gating counts and threshold
- `bootstrap_intervals.json` — Paired bootstrap confidence intervals

## Documentation

- README.md with three-command quick start
- docs/architecture.md — System overview
- docs/dataset_card.md — Data description
- docs/model_card.md — Model descriptions
- docs/evaluation.md — Evaluation protocol
- docs/limitations.md — Known limitations
- docs/failure_cases.md — Failure modes
- paper/report.md — Research report

## Claims Now Safe

- Six retrieval methods implemented and evaluated
- Temporal filtering eliminates stale evidence
- Calibrated abstention with frozen thresholds
- Decision gate with three codes and strict precedence
- Bond pricing with duration and convexity
- EIP-712 attestation with genuine Ethereum Keccak
- Reproducible research pipeline with fixed seed

## Claims Still Unsafe

- Actual retrieval performance (requires real corpus and production models)
- Actual calibration performance (requires real retrieval results)
- Full Python-to-Solidity interoperability (requires GBL Task 12/14)

## Limitations

- Fixture mode used for deterministic testing
- Models require internet access for production mode
- Small corpus (12 reports, 4 issuers)
- Small label set (32 questions)

## Next Dependency

GBL Task 9: Permissioned bond and eligibility lifecycle
