# E3 — Temporal and Contradiction-Aware Retrieval over SEC EDGAR

**Experiment:** e3-temporal-contradiction
**Date:** 2026-08-06
**Status:** INTERNAL PILOT — results valid on the SEC EDGAR XBRL facts described below.
**Reproduction:** `python scripts/run_e3_temporal.py` (writes
`research/results/e3_temporal_summary.json`).
**Commit:** branch `feat/e3-temporal-contradiction`.

---

## 1. Research Question

> Does adding source time, valid time, and document version reduce using expired
> or future information, and does it catch restatement contradictions?

**Falsifiable hypotheses:**

- H1: Source-time filtering (filed ≤ cutoff) eliminates future information.
- H2: Valid-time filtering (end ≤ valid_at) eliminates expired evidence.
- H3: Contradiction detection (prefer latest filed version per concept+period)
  improves contradiction F1 over plain retrieval.
- H4: Dense hybrid retrieval (semantic) helps temporal retrieval.

## 2. Data

SEC EDGAR XBRL `companyfacts` for AAPL, MSFT, KO (public domain, no API key,
descriptive User-Agent required; cache-only):

- 73,802 temporal facts (10-K / 10-Q / 10-K/A), valid time = `end`, source time = `filed`.
- 5,752 real temporal questions constructed from the data:
  - `old_vs_new` (4,786): same concept reported in adjacent fiscal years with
    different values.
  - `amended_vs_original` (34): same (concept, period) with a 10-K and a 10-K/A
    of different value (real restatements).
  - `cross_period` (932): same concept reported both annually and quarterly.
- Stratified sample of 234 questions for evaluation (100 old_vs_new + 34 amended
  + 100 cross_period).

## 3. Method

Five retrieval baselines over the fact corpus (query = question text, corpus
filtered by ticker, BM25 ranking, top-k=5):

| ID | Method | Temporal filter |
|---|---|---|
| B1 | Plain BM25 | none |
| B2 | BM25 + dense bi-encoder RRF | none |
| B3 | BM25 + **source-time filter** (filed ≤ source_cutoff) | future info removed |
| B4 | BM25 + **valid-time filter** (end ≤ valid_at) | expired info removed |
| B5 | BM25 + valid-time + **contradiction detection** (latest filed per concept+end) | + restatement-aware |

**Metrics:** future-information rate@k, expired-evidence rate@k, valid-evidence
recall@k, contradiction detection F1 (retrieved fact whose concept+period has
multiple filed values vs gold amended facts).

## 4. Results (234 sampled questions)

| Method | Future rate | Expired rate | Valid recall | Contra F1 |
|---|---|---|---|---|
| B1 BM25 | 0.339 | 0.089 | 0.526 | 0.101 |
| B2 dense hybrid | 0.397 | 0.257 | 0.504 | 0.055 |
| **B3 +source filter** | **0.000** | 0.161 | 0.491 | 0.124 |
| **B4 +valid filter** | 0.339 | **0.000** | **0.543** | 0.102 |
| **B5 +contradiction** | 0.585 | 0.000 | 0.538 | **0.178** |

## 5. Findings

1. **H1 supported.** B3 eliminates future information entirely (0.339 → 0.000).
   Source-time filtering is necessary and sufficient for the no-future-information
   property.
2. **H2 supported.** B4 eliminates expired evidence (0.089 → 0.000) and achieves
   the best valid-evidence recall (0.543). Valid-time filtering both removes
   wrong-period evidence and helps retrieval.
3. **H3 supported.** B5's contradiction detection F1 (0.178) is the highest of
   all methods, more than B1 (0.101). Restatement awareness genuinely improves
   contradiction identification.
4. **H4 NOT supported.** Dense hybrid (B2) did not beat plain BM25 on this
   corpus (valid recall 0.504 vs 0.526; expired rate worse 0.257 vs 0.089).
   The concept-name-in-query structure makes lexical BM25 already strong, and
   the dense signal added noise (retrieved semantically-similar but
   time-invalid facts). A valuable negative result.
5. **B5 trade-off (honest):** contradiction detection raises future rate
   (0.585) because deduplicating to the latest-filed version per concept+period
   surfaces late-filed corrections whose `filed` exceeds the question's
   `source_cutoff`. This is a real design trade-off between contradiction
   awareness and no-future-information, not a bug — B5 alone should not be used
   where the no-future property is mandatory (combine with B3's source filter).

## 6. Limitations

1. **Amended class is small (34)** — contradiction F1 has limited statistical
   power (the real restatement count in 3 companies).
2. **Stratified sample (234)** rather than full 5,752 for compute reasons.
3. **Question construction embeds the concept name** in the query, making
   retrieval partially lexical; natural-language paraphrases would stress
   semantic retrieval more (likely to change H4's outcome — future work).
4. **No cross-validation / CIs** on the temporal metrics yet (E1's bootstrap
   machinery could be applied; future work).
5. **SEC data is public-domain but cache-only** in this workspace; redistribution
   policy must be confirmed before any public release.

## 7. Claims Permitted After This Experiment

- **SUPPORTED:** Source-time filtering eliminated future information on SEC
  XBRL facts (0.339 → 0.000).
- **SUPPORTED:** Valid-time filtering eliminated expired evidence (0.089 →
  0.000) and maximized valid-evidence recall (0.543).
- **SUPPORTED:** Contradiction-aware retrieval (latest-filed dedup) improved
  contradiction F1 over plain BM25 (0.178 vs 0.101) on real restatements.
- **SUPPORTED (negative):** Dense hybrid did not beat BM25 on this corpus.
- **PROHIBITED:** "production-ready temporal system", "solves restatement
  detection", "no future information possible", "state-of-the-art".

## 8. Reproduction

```bash
cd EcoQuant-Financial-Intelligence
python scripts/run_e3_temporal.py   # needs research/cache/sec/*_companyfacts.json
```

- SEC raw data cache-only; public domain with descriptive User-Agent.
- Seeds: BM25 fixed; dense model all-MiniLM-L6-v2 (E1 asset).
