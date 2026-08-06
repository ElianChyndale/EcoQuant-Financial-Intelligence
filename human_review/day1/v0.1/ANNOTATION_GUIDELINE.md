# Day-1 Annotation Guideline — Single-Researcher Validation Pilot

**Freeze date:** 2026-08-06 (hashed in QUEUE_MANIFEST.json — do not edit after
freeze; edits invalidate the frozen hash)

**Scope:** This is a **pilot**, not a human study. One researcher. No
inter-rater agreement. No statistical significance. No paper headline.

---

## 1. What this pilot is

| Deliverable | Count | Status at freeze |
|---|---|---|
| SEC base cases (human verification) | 22 | PENDING_HUMAN_LABEL |
| Paired evidence conditions (stratified, 2 × 6 conditions) | 12 | PENDING_HUMAN_LABEL |
| Blind within-reviewer repeats | 5 | PENDING_HUMAN_LABEL (second pass only) |
| Interface usability cases (3 answer-only, 3 top-k, 3 package) | 9 | PENDING_HUMAN_LABEL |
| VISTA-Fin low-capacity exploratory run | 1 | INSUFFICIENT_DATA_FOR_TRAINING until labels freeze |
| Audit + claim-boundary reports | 2 | written at pilot close |

## 2. Non-negotiable rules

1. Never generate, infer, fill, or modify human labels.
2. Never display candidate labels, system predictions, model scores, or prior
   annotations before the researcher's first-pass label is frozen.
3. AI may validate schema and evidence-ID existence only.
4. Human signatures require explicit researcher action.
5. This work is a pilot, not a human study.
6. No inter-rater agreement may be claimed (single reviewer).
7. No statistical significance may be reported.
8. Gold-derived values are never used as model inference features.
9. No tuning on held-out issuer results.
10. All unresolved and ambiguous cases are preserved.

## 3. Review surface and blinding

- The **only sanctioned display surface** is `REVIEWER_SHEET.md`. It shows
  questions, evidence descriptors, and tokens — never candidate answers,
  scores, gold labels, or condition identities.
- `QUEUE_MANIFEST.json` has `sealed` and `reviewer_view` sections. **Do not
  open the `sealed` section** until your first-pass labels for the affected
  queue are frozen and saved.
- Paired cases use neutral tokens (`pr-01`…`pr-12`); condition identity is
  hidden. Some evidence IDs may hint at provenance (e.g. `-amended`): record
  your judgement independently, from the evidence, not from the hint.
- Blind repeats use `br-01`…`br-05`; the underlying case is not visible.

## 4. Workflow

1. **Read** this guideline and `SCHEMA.md`.
2. **First pass — 22 base cases.** For each row in `REVIEWER_SHEET.md` §"22
   base cases", verify against the primary source:
   - SEC XBRL company facts: `research/cache/sec/<ticker>_companyfacts.json`
     (cache-only; consult locally, never commit);
   - Full 10-K HTML: `research/cache/sec/full_10k/<ticker>-10k.htm`.
   Fill one JSONL record per case in `BASE_22_HUMAN_SIGNED.jsonl` with every
   field from `SCHEMA.md` §A. Freeze pass 1 before anything else.
3. **Paired cases — 12.** Same procedure for `PAIRED_12_HUMAN_SIGNED.jsonl`
   using the `pr-XX` tokens. Do not try to guess the condition; judge the
   evidence as presented.
4. **Interface pilot — 9.** Fill `INTERFACE_PILOT_9.jsonl` (fields in
   `SCHEMA.md` §C). Record the interface judgement, detected errors, missing
   evidence, wrong period, review time, confidence, notes. Label the section
   `SINGLE_REVIEWER_USABILITY_PILOT` and
   `NO_HUMAN_EFFECTIVENESS_CLAIM`.
5. **Blind repeat — 5.** After all 22 base labels are frozen, wait ≥ 4 hours
   (or overnight) if possible, then re-annotate the 5 `br-XX` rows **without
   looking at your first pass**. Record `"pass": 2`. Do not revise first-pass
   labels to increase agreement.
6. **Reliability.** Run `python -m experiments.a9_human.run_day1 reliability`
   — descriptive stats only (Cohen's kappa carries a small-sample warning;
   evidence-set Jaccard; entity/period/unit/numeric agreement).
7. **VISTA pilot.** After base labels are frozen and signed, run
   `python -m experiments.a9_human.run_day1 vista`. If eligibility is not
   met, the run honestly reports `INSUFFICIENT_DATA_FOR_TRAINING`.
8. **Researcher reflection.** Fill `RESEARCHER_REFLECTION.md` (it is an
   empty template by design — the researcher writes it personally).

## 5. Judgement policy

- `REVIEW_UNRESOLVED` is an allowed value on every categorical field. Never
  force a confident answer.
- If the evidence is genuinely ambiguous or the source is unavailable, mark
  it unresolved and explain in `reviewer_notes`. Unresolved cases are
  preserved, counted, and reported — never silently dropped.
- Sufficiency is judged against the **mandatory requirements** you identify
  for the question, not against any pre-computed set.

## 6. Signing

- Every record must set `signed_by` (your identifier), `timestamp`
  (ISO-8601 UTC), and `elapsed_seconds`. `signed_by` + `timestamp` is the
  signature; `signed: true` is an optional explicit acknowledgment.
- AI never sets these fields. A record without them does not count as a
  human label anywhere in the pipeline (enforced by the VISTA gate).

## 7. After the pilot

- Produce: `DAY1_HUMAN_VALIDATION_REPORT.md` and
  `DAY1_CLAIM_BOUNDARIES.md` (templates exist under `research/reports/`).
- Do not mark A9 COMPLETE. Do not rename the pilot a study.
- Permitted status vocabulary: `HUMAN_VERIFIED_PILOT` (only if all 22 signed
  and frozen), `12_CASE_HUMAN_VALIDATED_PILOT` (only if all 12 signed),
  `SINGLE_REVIEWER_PILOT_COMPLETE` / `FULL_STUDY_PENDING`,
  `PILOT_TRAINED_EXPLORATORY` / `INSUFFICIENT_DATA_FOR_TRAINING`.

## 8. Data hygiene

- Raw SEC cache (`research/cache/`) is gitignored. Never commit it.
- No private reviewer information in any record.
- All records are human-readable JSONL; review each file before commit.
