# E8 — EcoQuant System Integration

**Experiment:** e8-ecoquant-integration
**Date:** 2026-08-06
**Status:** INTERNAL PILOT — comparison on 6 public commercial questions.
**Reproduction:** `python scripts/run_e8_integration.py` (writes
`research/results/e8_integration_summary.json`).
**Commit:** branch `feat/e8-ecoquant-integration`.

---

## 1. Research Question

> Do the research-validated retrieval, verification, and routing mechanisms
> replace EcoQuant's unsupported prompt-only honesty score — and how do the
> two systems compare on repeatability, stability, refusal quality, and
> unsupported-answer handling?

**Falsifiable hypotheses:**

- H1: The proposed evidence pipeline produces citations (legacy produces none).
- H2: The proposed pipeline routes uncertain cases to review (legacy never does).
- H3: Both systems are deterministic (repeatable), but only the proposed one is
  evidence-grounded.

## 2. Systems Compared

**Legacy** (faithful reimplementation of the archival EcoQuant logic):
- Prompt-only LLM honesty score (0-100) from the question alone; mocked
  deterministically by seeded hash.
- Fixed spread formula: `(60 - score) * 2` bps.
- No evidence, no citation, no verification, never routes to review
  (`review_status = "auto"` always).

**Proposed** (reuses E1-E7 validated components):
1. E1 BM25 retrieval → top evidence pages (FinanceBench corpus).
2. E7 concept resolution → SEC XBRL facts for the ticker/year.
3. E4 multi-layer verification → SUPPORTED / REVIEW_REQUIRED / INSUFFICIENT /
   CONFLICTING.
4. E5-style calibrated confidence (deterministic from retrieval margin).
5. `decide()` gate → AUTO_REPORT / HUMAN_REVIEW_REQUIRED / INSUFFICIENT_EVIDENCE.
6. On AUTO_REPORT: build `RiskAttestationV1` (signed evidence package).

**Boundary (enforced):** the AI produces attestation + evidence + confidence +
review status. It NEVER sets a credit spread, loan amount, liquidation, or
transfer — those are deterministic business-rule outputs outside this component.

## 3. Results (6 commercial questions)

| Metric | Legacy | Proposed |
|---|---|---|
| Citation validity | **0.000** | **1.000** |
| Refusal quality (routed to review) | **0.000** | **0.667** |
| Repeatability | 1.000 | 1.000 |
| Decision distribution (proposed) | — | 2 AUTO_REPORT, 4 HUMAN_REVIEW_REQUIRED |

## 4. Findings

1. **H1 supported.** Citation validity 0 → 1.0: the legacy system never cites
   evidence; the proposed pipeline always produces a source-linked evidence
   bundle (retrieval pages + resolved XBRL facts).
2. **H2 supported.** Refusal quality 0 → 0.667: the proposed gate routes 4/6
   complex commercial questions to human review (correct conservative
   behavior); the legacy system auto-reports everything with no evidence.
3. **H3 supported.** Both are repeatable (1.0), but only the proposed system is
   evidence-grounded: its decisions are traceable to retrieval pages + XBRL
   facts + verification layers.
4. **Boundary held.** The proposed pipeline never outputs a spread — it emits
   attestation + evidence + confidence + review status; the deterministic gate
   decides. This is the architecture the programme requires.

**Interpretation:** the legacy system's failure is structural (no evidence
input, no review routing), not a tuning issue. The proposed pipeline fixes the
structural gaps with validated components while enforcing the AI/non-AI
boundary. The 2 AUTO_REPORT cases (likely the simplest questions) demonstrate
the gate can auto-accept when evidence is strong; the 4 review cases are the
conservative remainder.

## 5. Limitations

1. **Small case set (6)** — a demonstration, not a statistical comparison.
2. **Legacy LLM mocked** (seeded hash) — the real legacy output varied per
   prompt; the mock captures its structural behavior (no evidence, no review).
3. **Confidence is a deterministic proxy** (retrieval margin), not the full E5
   Platt calibration on this question set.
4. **No end-to-end signed attestation verification** in the runner (attestation
   is built; signature verification is covered by existing SOL-3 tests).
5. **Public questions only** — no private cases.

## 6. Claims Permitted After This Experiment

- **SUPPORTED:** The proposed evidence pipeline produces citations and routes
  uncertain cases to review; the legacy prompt-only score does neither.
- **SUPPORTED:** The integration boundary holds — AI produces attestation +
  evidence + confidence + review status; it never sets a spread.
- **SUPPORTED (negative):** The legacy honesty-score → spread formula is
  structurally unsupported (no evidence, no review); the comparison quantifies
  the upgrade.
- **PROHIBITED:** "production-ready", "replaces human credit analysts",
  "regulatory-grade decision system".

## 7. Reproduction

```bash
cd EcoQuant-Financial-Intelligence
python scripts/run_e8_integration.py   # needs financebench + sec cache
```

- Fully deterministic; no stochastic components.
