# human_review/day1 — Solo Provisional Annotation Pilot

**Status (2026-08-07): 20 CASES ANNOTATED AS SOLO_PROVISIONAL.**

> Solo annotations are **provisional research labels** and are **not treated
> as independently validated gold labels**. They are traceable,
> re-checkable, and independently overridable by a future annotator.

## Status lifecycle

```text
CANDIDATE_UNREVIEWED → SOLO_PROVISIONAL → SOLO_CONFIRMED / SOLO_DISAGREEMENT
                     → NEEDS_EXTERNAL_REVIEW → DOUBLE_ANNOTATED
                     → ADJUDICATED → HUMAN_VALIDATED_GOLD
```

| Status | Meaning |
| --- | --- |
| `CANDIDATE_UNREVIEWED` | machine-generated, no human judgement yet |
| `BLOCKED_EVIDENCE_INCOMPLETE` | page insufficient to annotate |
| `SOLO_PROVISIONAL` | one blind solo pass complete (Green) |
| `SOLO_CONFIRMED` | delayed re-check agrees |
| `SOLO_DISAGREEMENT` | same annotator, two rounds differ |
| `NEEDS_EXTERNAL_REVIEW` | high risk — give to a second annotator first |
| `DOUBLE_ANNOTATED` | two independent annotators |
| `ADJUDICATED` | disagreement resolved |
| `HUMAN_VALIDATED_GOLD` | usable as gold |

## Current annotated cases (SOLO_ANNOTATIONS.jsonl, append-only)

| Count | Status | Route |
|---|---|---|
| 17 | SOLO_PROVISIONAL | 16 ANSWER + 1 ABSTAIN |
| 3 | NEEDS_EXTERNAL_REVIEW | 3 REVIEW |

20 cases annotated (10 reference sheets + 10 extension cases). Every record
includes the evidence-package hash, raw human Q1-Q5 choices, machine-derived
labels (kept separate), and the machine verification result (all MATCH).

## How to work (conversational solo annotation)

1. Present a case (reads the SOURCE FILE from disk at call time):

   ```bash
   python scripts/solo_annotate.py present <case_id>
   ```

2. Answer Q1-Q5 (question clarity / evidence / inputs+calc / issue flags /
   route+confidence). The machine verifies AFTER you submit (anti-anchoring)
   and reports only differences.

3. Records append to `SOLO_ANNOTATIONS.jsonl`; status per risk layering
   (Green → SOLO_PROVISIONAL, Red → NEEDS_EXTERNAL_REVIEW).

4. Delayed re-check after 5-7 days (blind): compare round 1 vs round 2 →
   SOLO_CONFIRMED / SOLO_DISAGREEMENT.

## Contents

| File | Purpose |
|---|---|
| `QUEUE_MANIFEST.json` | Frozen v0.2-draft queues + hashes (21 cases). |
| `FROZEN.sha256` | SHA-256 of frozen components. |
| `SOLO_ANNOTATIONS.jsonl` | **Append-only solo annotation records** (the active labels). |
| `EXTENSION_40_cases.json` | 40 extension cases beyond the 10 reference sheets. |
| `EXTENSION_40.txt` | case_id list of the 40 extension cases. |
| `reference_sheets/` | 10 candidate reference sheets (human-readable). |
| `BASE_HUMAN_SIGNED.jsonl` | Legacy v0.2-draft sign file (kept empty; solo records are authoritative). |

## Honesty markers

`EXPLORATORY_PILOT · SMALL_SAMPLE · NOT_PAPER_HEADLINE`

Solo annotations are provisional research labels; they are not gold until a
second annotator independently re-annotates and disagreements are adjudicated.
