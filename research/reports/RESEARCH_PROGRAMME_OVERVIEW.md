# Evidence-to-Decision Financial AI Research Programme — Overview

**Programme:** Evidence-to-Decision Financial AI Research Programme
**Date:** 2026-08-06
**Status:** INTERNAL RESEARCH COMPLETE (E0-E8) — all results on public data;
private cases explicitly excluded.
**Reproduction:** each experiment has a one-command runner
(`scripts/run_e{0,1,2,3,4,5,7,8}_*.py`); all write machine artifacts under
`research/results/` and are wired into the portfolio release checks.

---

## 1. Central Thesis

> Financial and commercial document intelligence systems become reliable not by
> adding model capability, but by **structuring the evidence-to-decision path**:
> evidence retrieval, deterministic verification, uncertainty calibration, and
> explicit human-review routing — with a hard boundary that AI produces
> attestations and review status, never financial actions.

## 2. Research Question

> How can retrieval, table/numerical reasoning, temporal contradiction
> handling, deterministic verification, uncertainty calibration, selective
> abstention, and human oversight combine to produce more reliable
> decision-support outputs from financial documents?

## 3. Programme Architecture

```
Documents
→ Evidence Retrieval (E1)           → top evidence pages
→ Structured Extraction (E2, E7)    → table cells / XBRL facts with source IDs
→ Numerical & Temporal Verification (E3, E4)
                                     → valid/source-time filtering, claim verification
→ Uncertainty Calibration (E5)      → calibrated confidence, risk-coverage
→ Human Review Routing (E5, E8)     → AUTO_REPORT / REVIEW / INSUFFICIENT
→ Evidence Package (E8)             → RiskAttestationV1 + evidence bundle
→ Deterministic Business Rules      → approval gate (AI never sets spread)
```

## 4. Experiments and Results

| Exp | Question | Data | Key result |
|---|---|---|---|
| E0 | Is the benchmark leakage-free and reproducible? | EcoQuant corpus + FinanceBench | gold-separated adapters, leakage tests, one-command integrity validator |
| E1 | Does hybrid beat single retrieval on real docs? | FinanceBench 150q | dense 0.563 > hybrid 0.511 > sparse 0.29-0.38 R@5; method preference reverses across datasets (H1/H3 rejected) |
| E2 | Does separating calc from retrieval help tables? | GRI-QA 266q | known-table deterministic calc: 94% within 1%; retrieval is the bottleneck (B7 0.70 vs B3 0.50) |
| E3 | Do source/valid-time filters reduce temporal errors? | SEC XBRL 3 companies | source filter eliminates future info (0.34→0); valid filter eliminates expired (0.09→0); contradiction F1 +76% |
| E4 | Does post-generation verification reduce unsupported answers? | FinanceBench + GRI-QA | false-pass rate 0.000; scale-normalized matching necessary; presence ceiling 37% (derived answers) |
| E5 | Does calibrated confidence enable selective prediction? | FinanceBench retrieval | AUROC 0.923; ECE 0.054; at 90% precision only 0.6% coverage — calibration certifies, doesn't create precision |
| E7 | Does the method generalize to commercial analysis? | SEC XBRL 6 companies, 4 domains | source-linked margins/FCFF/ROIC; values match public financials; honest None for missing evidence |
| E8 | Does the evidence pipeline replace the prompt-only score? | 6 commercial cases | citation 0→1.0; review routing 0→0.67; boundary held (AI never sets spread) |

## 5. Cross-Experiment Findings

1. **Retrieval quality is the binding constraint.** E1 (method preference
   reversal), E2 (B7 vs B3 gap), and E5 (0.6% coverage at 90% precision) all
   converge: no downstream component (calculation, calibration, verification)
   can compensate for retrieval misses. The research programme's central
   engineering implication: **improve retrieval first**.
2. **Deterministic verification is strong on its own.** E2's separated
   calculation reaches 94% tolerance accuracy with no LLM; E4's verifier has
   zero false-pass on injected unsupported answers. The "deterministic core"
   is reliable; the LLM is not needed for it.
3. **Honest negative results are the programme's strength.** E1's hybrid
   reversal, E3's dense-hybrid non-improvement, E4's presence ceiling, E5's
   coverage floor — each is a falsifiable hypothesis that was tested and
   either rejected or bounded. No result is hidden or inflated.
4. **Fiscal/period reality matters.** E7's heterogeneous fiscal years (Sep/Jun/
   Dec ends) and E3's restatement semantics show that financial data requires
   explicit temporal handling — generic "recentcy" or "same year" assumptions
   are wrong.
5. **The AI/non-AI boundary is enforceable.** E8 demonstrates the pipeline
   emits attestation + evidence + confidence + review status; the deterministic
   gate decides approval. This is the architecture the programme requires for
   decision support.

## 6. Data Assets (public, cache-only)

| Dataset | Content | License | Evidence |
|---|---|---|---|
| EcoQuant corpus | 64 questions, 12 green-bond reports | public docs, cache-only | E0/E1 |
| FinanceBench sample | 150 questions, 168 pages, 32 companies | unconfirmed → cache-only | E0/E1/E4/E5 |
| GRI-QA quant | 266 questions, 27 tables, 9 companies | MIT | E2/E4 |
| SEC XBRL companyfacts | 6 companies, 4 domains, 73k+ facts | public domain | E3/E7/E8 |

All raw data is gitignored cache; hashes + derived metadata committed. Dataset
cards document license, page conventions, and known quirks.

## 7. Failure Analysis Summary

- E1: hybrid not universally better; dense/semantic phrasing interaction.
- E2: sign ambiguity for increase functions (~5% residual); percentage-average
  absolute-value semantics; grid-region cells.
- E3: dense hybrid added noise on concept-name queries; contradiction-aware
  dedup raises future-rate (trade-off, documented).
- E4: 63% of FinanceBench answers are derived, not extracted — presence
  verification bounded at 37%.
- E5: top-1 retrieval accuracy 18% bounds selective coverage.
- E7: heterogeneous GAAP naming and fiscal years; missing disclosures (JNJ
  operating income, EQIX gross profit) handled as honest None.

## 8. Limitations

1. **No LLM in the loop** — all components are deterministic/retrieval-based;
   generative verification (LLM-as-judge) is future work.
2. **No human review study** (E6) — the programme's manual-review step requires
   the researcher's own judgment; not automated.
3. **Benchmark contamination risk** — FinanceBench/GRI-QA are public; model
   training data may contain them (relevant only if an LLM is later added).
4. **No statistical significance claims** — CIs reported (E1) but effect
   sizes are modest and sample sizes small; the programme reports honest
   bounds, not significance.
5. **Single-machine reproducibility** — Windows environment; cross-platform CI
   exists for unit tests, not for the data-dependent runners.

## 9. Claim Boundaries

| Level | Examples |
|---|---|
| SUPPORTED | Dense > sparse on FinanceBench; source-filter removes future info; false-pass 0.0; boundary holds |
| PARTIALLY SUPPORTED | Dense > hybrid (CI overlap); coverage at 90% precision (small) |
| NEGATIVE RESULTS | Hybrid not always best; calibration doesn't fix retrieval; presence verification bounded |
| PROHIBITED | state-of-the-art, production-ready, eliminates hallucinations, generalises to finance, statistically significant |

## 10. Reproduction

```bash
cd EcoQuant-Financial-Intelligence
python scripts/run_e0_validate.py       # E0 integrity
python scripts/run_e1_retrieval.py      # E1 retrieval baselines
python scripts/run_e2_table.py          # E2 table reasoning
python scripts/run_e3_temporal.py       # E3 temporal contradiction
python scripts/run_e4_verification.py   # E4 evidence verification
python scripts/run_e5_calibration.py    # E5 selective prediction
python scripts/run_e7_commercial.py     # E7 commercial analysis
python scripts/run_e8_integration.py    # E8 integration comparison
```

Requires cache-only data under `research/cache/` (see dataset cards).

## 11. Next Steps

1. **E6 human review** (researcher-driven, not automatable): stratified manual
   review of 100-200 cases with inter-rater agreement.
2. **LLM-as-judge integration**: combine the deterministic verifier with a
   generative verifier for derived answers (E4 ceiling).
3. **Full retrieval improvement**: dense + reranker on FinanceBench (B6
   unblocked), which E5 predicts will lift selective coverage.
4. **Workshop-paper write-up**: this overview + per-experiment reports form the
   evidence base for a submission.
