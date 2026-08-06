# human_review/day1 — Single-Researcher Validation Pilot

Status at freeze (2026-08-06): **PREPARATION COMPLETE · HUMAN LABELS
PENDING**. Nothing in this directory is a human label yet.

## Contents

| File | Purpose |
|---|---|
| `QUEUE_MANIFEST.json` | Frozen queues + hashes. `sealed` = audit content (candidate answers, gold, condition map) — **keep closed during review**. `reviewer_view` = display-safe. |
| `FROZEN.sha256` | SHA-256 of every frozen component + total. |
| `ANNOTATION_GUIDELINE.md` | Frozen researcher-facing protocol (hashed in the manifest). |
| `SCHEMA.md` | Record schemas for all four human-record files. |
| `REVIEWER_SHEET.md` | The only sanctioned display surface. |
| `BASE_22_HUMAN_SIGNED.jsonl` | Empty. Researcher fills + signs. |
| `PAIRED_12_HUMAN_SIGNED.jsonl` | Empty. Researcher fills + signs. |
| `BLIND_REPEAT_5.jsonl` | Empty. Two passes (`pass: 1`, `pass: 2`). |
| `INTERFACE_PILOT_9.jsonl` | Empty. Researcher fills + signs. |
| `INTRA_RATER_RELIABILITY.md` | Methodology + status (NO_DATA until both passes). |
| `ANNOTATION_DISAGREEMENTS.md` | Template; preserves unresolved/ambiguous cases. |
| `RESEARCHER_REFLECTION.md` | Empty structured template — researcher writes it. |

## How to work

1. `python -m experiments.a9_human.run_day1 verify` — confirm hashes match
   before you start.
2. Annotate using `REVIEWER_SHEET.md`; never open the `sealed` section of
   the manifest before first-pass labels are frozen.
3. After signing, re-run `verify` (hashes unchanged — human records are NOT
   hashed components; the queues must not change).
4. `python -m experiments.a9_human.run_day1 reliability`
5. `python -m experiments.a9_human.run_day1 vista`

## Rules (summary)

AI never fills, infers, or signs human labels. No inter-rater claims. No
significance claims. No A9 COMPLETE status. Unresolved cases are preserved.
