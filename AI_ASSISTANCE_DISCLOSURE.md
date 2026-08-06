# AI Assistance Disclosure

**Date:** 2026-08-06
**Scope:** This repository (EcoQuant-Financial-Intelligence) and the FinVEST
research programme it contains.

---

## What AI coding assistants were used for

AI coding assistants (Claude Code, and earlier tooling) were used for:

- implementation scaffolding,
- refactoring,
- test generation,
- experiment orchestration (runner scripts, result artifacts),
- documentation drafting,
- static audit support (e.g. identifying the E5 gold-feature leakage).

## What the researcher retains responsibility for

The researcher (Elian) retains full responsibility for:

- research-question formulation;
- hypothesis and metric selection;
- dataset inclusion decisions;
- annotation guidelines;
- human gold-label validation;
- leakage diagnosis and remediation decisions;
- interpretation of results;
- claim approval;
- paper arguments and limitations.

## Status of AI-generated outputs

AI-generated outputs are treated as **unverified proposals** until they are
tested, audited, or manually reviewed. Specifically:

- Code is verified by the test suite and CI gates.
- Experiment results are verified by the release validator and integrity
  gates (A0).
- Benchmark cases built automatically (e.g. SEC XBRL cases) are **candidate
  cases**; they become gold only after human annotation and adjudication.
- Human-study labels are entered and signed by human reviewers only; AI never
  fabricates human annotations.

## Known AI-assisted findings requiring human confirmation

- The E5 gold-feature leakage was identified by audit; the researcher
  confirmed and approved the invalidation and remediation.
- The FinVEST benchmark's 2,000-case target and paired-condition design follow
  a plan drafted with AI assistance; dataset inclusion and annotation rules
  are researcher-decided.

## Non-negotiable boundaries

- No private commercial documents, raw reviewer identities, restricted
  datasets, API keys, or model weights are committed to this repository.
- Raw SEC/FinanceBench/GRI-QA data is cache-only (gitignored); only hashes and
  derived metadata are committed.
- AI never sets credit spreads, approves lending, transfers funds, liquidates
  collateral, or executes trades — the integration boundary is enforced.
