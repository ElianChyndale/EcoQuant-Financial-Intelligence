# Day-1 Human-Validation Pilot — Status Report

**Date:** 2026-08-06
**Branch:** `research/day1-human-validation-pilot`
**Overall status:** `PREPARATION_FROZEN` · `HUMAN_LABELS_PENDING`
**Honesty markers:** `EXPLORATORY_PILOT` · `SMALL_SAMPLE` · `NOT_PAPER_HEADLINE`

> This report documents a bounded, single-researcher validation pilot for
> FinVEST. It is NOT the full A9 human study, NOT a paper-level VISTA-Fin
> experiment, and NOT independent inter-annotator validation. **No human
> labels exist yet; no human-verification claim is made in this report.**

---

## 1. What was frozen (all hashed in `human_review/day1/QUEUE_MANIFEST.json`)

| Component | Content | Status |
|---|---|---|
| Annotation guideline | `ANNOTATION_GUIDELINE.md` (SHA-256 in manifest) | FROZEN |
| 22 base-case queue | SEC XBRL cases from `sec_cases` builder (6 tickers: AAPL, MSFT, KO, EQIX, JNJ, UPS; 8 derived, 2 amended, 12 unanswerable) | FROZEN (candidate) |
| 12 paired-condition queue | 2 per condition across PARTIAL_MISSING_INPUT, OUTDATED, FUTURE_LEAK, WRONG_PERIOD, CONFLICTING, DISTRACTOR | FROZEN |
| 5 blind-repeat selection | `br-01`…`br-05` (see §4), shuffled order, seeded | FROZEN |
| 9 interface-pilot cases | distinct base questions; 3 answer-only, 3 answer+top-k pages, 3 answer+VISTA package | FROZEN |
| Split manifest | leave-one-issuer-out × 6 folds; grouped by issuer + base question (isolation levels 1 & 4) | FROZEN |
| Experiment config | P1 low-capacity logistic selector; 3 seeds (20260806/07/08); inference-time features only; B1–B4 baselines; 6 metrics; eligibility ≥12 signed labels across ≥3 issuers | FROZEN |

Freeze verification: `python -m experiments.a9_human.run_day1 verify` →
`verified: true`, 0 violations, 9 components checked.

## 2. Blinding and contamination controls

- Reviewer surface is `REVIEWER_SHEET.md` only; the manifest's `sealed`
  section (candidate answers, gold labels, condition map) stays closed until
  first-pass labels freeze (policy rule 2).
- Paired cases carry neutral tokens `pr-01`…`pr-12`; condition identity
  hidden. The generator's condition-embedding `instance_id` is never shown.
- Blind repeats hide case identity and prior labels.
- No candidate answer, system score, or prior annotation appears in any
  display surface (test-enforced).

## 3. Annotation scaffolding

`human_review/day1/` contains four **empty** JSONL record files
(`BASE_22_HUMAN_SIGNED.jsonl`, `PAIRED_12_HUMAN_SIGNED.jsonl`,
`BLIND_REPEAT_5.jsonl`, `INTERFACE_PILOT_9.jsonl`). Zero records exist
until the researcher fills and signs them (`signed_by` + `timestamp`).
The VISTA gate counts only signed records — enforced and tested.

## 4. Blind-repeat selection (seeded 20260806, deterministic)

| Temp ID | Underlying case |
|---|---|
| br-01 | finvest-UPS-fcff-2025 |
| br-02 | finvest-KO-fcff-2025 |
| br-03 | finvest-KO-insufficient-AccountsPayableOtherCurrent-2025 |
| br-04 | finvest-JNJ-fcff-2025 |
| br-05 | finvest-AAPL-amended-SalesRevenueNet-2009-03-28 |

## 5. Reliability and disagreement tooling

- `compute_intra_rater` is implemented and tested (Cohen's kappa with
  small-sample warning for n=5, evidence-set Jaccard, entity/period/unit
  agreement, numeric agreement with tolerance). It returns `NO_DATA` until
  both blind passes are frozen and signed.
- `ANNOTATION_DISAGREEMENTS.md` preserves every unresolved/ambiguous case;
  `RESEARCHER_REFLECTION.md` is an empty template for the researcher.
- No inter-rater claim and no significance claim are possible from this
  design and none will be made.

## 6. VISTA-Fin pilot

Runner implemented (`finvest.human_study.day1_pilot.run_vista_pilot`) and
gated: training starts only after ≥12 human-signed base labels across ≥3
issuers are frozen. Today's honest output (see
`artifacts/results/VISTA_PILOT_V0_1.json`, mirrored at
`research/results/vista_pilot_v0_1.json`):

- **status:** `INSUFFICIENT_DATA_FOR_TRAINING`
- human-verified labels: 0 across 0 issuers (required: ≥12 across ≥3)
- result: `null` — training skipped honestly

Design notes: leave-one-issuer-out × 3 seeds; grouped by issuer + base
question; P1 = pure-Python low-capacity logistic selector on 8
inference-time features (no gold-derived values, rule 8); B4 is an ILP
oracle upper bound, never headline; no test tuning (rule 9). The training
path is implemented and unit-tested with clearly-marked synthetic fixtures,
ready to run the day human labels freeze. Every result will carry
`EXPLORATORY_PILOT · SMALL_SAMPLE · NOT_PAPER_HEADLINE`.

## 7. Integrity gate

A pre-existing bug in `b3_beam_search` was fixed: the final answer was
taken from the last beam frontier only, so the best subset could be pruned
away. The selector now tracks the best subset across all frontiers. All
existing tests still pass.

## 8. What remains (human actions only)

1. Annotate + sign 22 base records (pass 1).
2. Annotate + sign 12 paired records.
3. Annotate + sign 9 interface records.
4. ≥4h gap, then annotate + sign 5 blind-repeat records (pass 2).
5. Run `reliability`, then `vista`.
6. Researcher fills `RESEARCHER_REFLECTION.md` and appends results to the
   reliability/disagreement documents.
7. Update statuses (see `DAY1_CLAIM_BOUNDARIES.md` for the allowed
   vocabulary) and close the pilot report.

## 9. Tests and gates at freeze time

- `pytest tests/finvest/` — 92 passed (66 pre-existing + 26 new).
- New files are ruff-clean and mypy-clean (5 pre-existing mypy errors in
  `html_parser.py`, `conditions.py`, `full_corpus.py` predate this branch;
  full-repo lint/type debt is documented in §10).
- `python -m experiments.a9_human.run_day1 verify` — clean.

## 10. Pre-existing repo gate debt (not introduced by this pilot)

- `ruff check .`: 77 pre-existing errors (52 F401 unused imports, 13 E741
  ambiguous names, 10 E402 imports-not-at-top, 2 F841).
- `mypy .`: 255 pre-existing errors across 42 files (config added to
  pyproject so the gate runs at all; all remaining errors predate this
  branch).
- Neither was touched in this pilot; the changes here introduce zero new
  violations (verified on the changed files).

## 11. Status vocabulary used

- FinVEST SEC 22 base cases: `CANDIDATE_QUEUE_FROZEN` → `HUMAN_VERIFIED_PILOT`
  (only after all 22 signed; **not yet**)
- Paired conditions: `12_CASE_QUEUE_FROZEN` → `12_CASE_HUMAN_VALIDATED_PILOT`
  (only after all 12 signed; **not yet**)
- Human study: `SINGLE_REVIEWER_PILOT_PREPARED` → `SINGLE_REVIEWER_PILOT_COMPLETE`
  / `FULL_STUDY_PENDING` (**A9 is NOT complete**)
- VISTA-Fin: `INSUFFICIENT_DATA_FOR_TRAINING` (today) →
  `PILOT_TRAINED_EXPLORATORY` (after labels)
