# Day-1 Claim Boundaries

**Date:** 2026-08-06
**Purpose:** every claim this pilot may or may not support, with evidence.
Update this matrix only when the researcher signs records or Elian approves.

---

## Claims this pilot CANNOT support (at any point)

| Claim | Why it is excluded |
|---|---|
| "Human study" / A9 results | Single reviewer, 22+12+5+9 records — a pilot, not the 24-30 reviewer study (policy rule 5) |
| Inter-rater agreement | One reviewer only (rule 6) |
| Statistical significance | n is tiny and the design forbids it (rule 7) |
| Benchmark gold quality (Krippendorff α ≥ 0.75, entity/period agreement ≥ 0.90) | Go/No-Go thresholds belong to the full benchmark; a 5-case blind repeat cannot estimate them (PREREGISTRATION §10) |
| VISTA-Fin headline numbers | Everything is `EXPLORATORY_PILOT · SMALL_SAMPLE · NOT_PAPER_HEADLINE`; B4 is oracle-conditioned and never headline |
| Any claim before signing | Records without `signed_by` + `timestamp` are not human labels |

## Claims that are TRUE today (verified)

| Claim | Evidence |
|---|---|
| 22 candidate SEC base cases exist, schema-validate, and are frozen | `QUEUE_MANIFEST.json` `base_22_queue` (22 records) + `verify_frozen` clean + tests |
| 12 paired instances stratified 2×6 conditions are frozen | manifest `paired_12_queue` + test `test_paired_queue_stratified_12` |
| 9 interface cases use distinct base questions, 3 per display condition | manifest `interface_9_cases` + test |
| 5 blind-repeat cases are selected deterministically (seed 20260806) | manifest `blind_repeat_5_selection` + test |
| Reviewer surfaces display no candidate labels / conditions | `test_reviewer_view_has_no_candidate_labels` |
| Human record files are EMPTY — no human label exists anywhere | all 4 JSONL files are 0 bytes |
| VISTA pilot cannot train today | `VISTA_PILOT_V0_1.json`: `INSUFFICIENT_DATA_FOR_TRAINING`, 0 labels |
| Queue hashes are reproducible | `verify_frozen` → 0 violations; `FROZEN.sha256` |
| The pilot introduces zero new lint/type violations | ruff + mypy clean on all changed files |

## Claims that become TRUE only after researcher action

| Claim | Gate |
|---|---|
| "22 SEC base cases human-verified (pilot)" | all 22 signed records frozen → status `HUMAN_VERIFIED_PILOT` |
| "12 paired conditions human-validated (pilot)" | all 12 signed → `12_CASE_HUMAN_VALIDATED_PILOT` |
| "Single-reviewer pilot complete" | all 36 records + 9 interface records signed; reflection written → `SINGLE_REVIEWER_PILOT_COMPLETE` |
| "VISTA-Fin exploratory pilot trained" | ≥12 signed base labels across ≥3 issuers + run completed → `PILOT_TRAINED_EXPLORATORY` |
| Descriptive intra-rater statistics | both blind passes signed → numbers into `INTRA_RATER_RELIABILITY.md` |

## Status vocabulary (binding)

| Status | Allowed only when |
|---|---|
| `HUMAN_VERIFIED_PILOT` | all 22 base records signed (not yet) |
| `12_CASE_HUMAN_VALIDATED_PILOT` | all 12 paired records signed (not yet) |
| `SINGLE_REVIEWER_PILOT_COMPLETE` | all pilot records signed + reflection (not yet) |
| `FULL_STUDY_PENDING` | pilot closed, full A9 study remains (then) |
| `PILOT_TRAINED_EXPLORATORY` | eligible VISTA run completed (not yet) |
| `INSUFFICIENT_DATA_FOR_TRAINING` | today's honest VISTA status (current) |
| `A9 COMPLETE` | **never from this pilot** |

## Boundaries on data and process

- Raw SEC cache is gitignored; only hashes and derived metadata are
  committed.
- No private reviewer information in any record.
- Unresolved/ambiguous cases are preserved and counted, never dropped.
- No gold-derived value enters any inference feature (rule 8).
- No tuning on held-out issuers (rule 9).
