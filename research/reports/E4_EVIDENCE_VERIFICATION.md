# E4 — Citation and Evidence Verification

**Experiment:** e4-evidence-verification
**Date:** 2026-08-06
**Status:** INTERNAL PILOT — results valid on the described benchmark.
**Reproduction:** `python scripts/run_e4_verification.py` (writes
`research/results/e4_verification_summary.json`).
**Commit:** branch `feat/e4-evidence-verification`.

---

## 1. Research Question

> Does adding citation + numeric verification after answer generation reduce
> unsupported answers — and can the verifier catch unsupported claims without
> rejecting too many supported ones?

**Falsifiable hypotheses:**

- H1: A multi-layer verifier (citation, number grounding, year/unit/scale,
  calculation, conflict) detects injected unsupported answers (low false-pass).
- H2: Scale-normalized number matching (billion/million/raw) is necessary —
  exact matching fails on paraphrased answers.
- H3: Supported-answer accuracy is bounded by whether the answer number is
  literally present in the cited evidence (extractive vs derived answers).

## 2. Data

Verification benchmark built from real data:

- **FinanceBench** (30 supported + 30 injected-unsupported cases): supported =
  gold answer + cited full pages; unsupported = same with wrong number injected
  (number NOT in evidence).
- **GRI-QA** (supported numeric cases): claim = calculated value, evidence =
  table question text.

## 3. Method

Six verification layers over each claim:

1. `citation_present` — ≥1 evidence cited.
2. `number_in_evidence` — every claim number grounded in ≥1 cited evidence
   (scale-normalized: "1.2 billion" ↔ "1200000000").
3. `year_consistent` — claimed year appears.
4. `unit_scale_consistent` — claimed unit/scale appears.
5. `calculation_reproducible` — supplied expected value matches claim numbers.
6. `no_conflict` — cited evidences don't disagree (restatement semantics).

Output states: SUPPORTED / REVIEW_REQUIRED / INSUFFICIENT_EVIDENCE /
CONFLICTING_EVIDENCE. Conservative resolution: the most restrictive failing
layer determines the state.

## 4. Results

| Metric | Value |
|---|---|
| Supported-answer accuracy | 0.333 (10/30) |
| **False-pass rate (critical)** | **0.000** (0/30) |
| Unsupported-rejected rate | 1.000 (30/30) |

State distribution: 50 INSUFFICIENT_EVIDENCE, 10 SUPPORTED (60 total).

**Ceiling analysis:** only **46/126 (37%)** of FinanceBench answers have numbers
that literally appear in their cited pages. The remaining 63% are *derived*
answers (ratios like 8.7%, capital-intensity 5.1/20.0, liquidity 3.0/0.96) —
the answer number is **computed, not extracted**.

## 5. Findings

1. **H1 strongly supported.** False-pass rate = 0.000: every injected
   unsupported answer was rejected (unsupported-rejected rate 1.000). The
   verifier never wrongly accepts an ungrounded number — the critical safety
   property.
2. **H2 supported.** Scale normalization was necessary: "1,577" in the page vs
   "$1577.00" in the answer only matched after normalization (supported
   accuracy 0.20 → 0.33).
3. **H3 supported.** Supported accuracy (0.33) is bounded by the extractive
   ceiling (0.37): answers whose numbers aren't literally in the cited text
   (derived/calculated values) cannot pass presence verification. This is a
   data reality, not a verifier bug.

**Interpretation:** verification is excellent at the critical task (never
passing unsupported numbers) but strict for derived answers. This motivates
the E2-style calculation verifier: derived answers should be verified by
reproducing the calculation from evidence numbers, not by presence matching.
The `calculation_reproducible` layer exists; wiring it to FinanceBench's
derived answers is future work.

## 6. Limitations

1. **Benchmark skew** — 30 supported + 30 injected-unsupported is a stress
   test of false-pass, not a real-world unsupported-answer base rate.
2. **Derived answers** (63% of FinanceBench) not verifiable by presence;
   calculation-based verification for them is future work.
3. **Exact-token matching** even after scale normalization misses semantic
   equivalence (e.g. "in the billions" vs a raw number).
4. **No LLM in the loop** — verifier is deterministic; a real system would
   combine it with generative answers.

## 7. Claims Permitted After This Experiment

- **SUPPORTED:** A multi-layer deterministic verifier rejected every injected
  unsupported answer (false-pass rate 0.000) on the benchmark.
- **SUPPORTED:** Scale-normalized matching is necessary for grounding
  paraphrased numeric answers.
- **SUPPORTED (negative):** Only ~37% of FinanceBench answers have numbers
  literally present in cited pages — presence verification alone cannot verify
  derived answers.
- **PROHIBITED:** "eliminates hallucinations", "verifies all financial
  answers", "production-grade verification".

## 8. Reproduction

```bash
cd EcoQuant-Financial-Intelligence
python scripts/run_e4_verification.py   # needs financebench/griqa cache
```

- Fully deterministic; no stochastic components.
