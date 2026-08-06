# Day-1 Pilot Record Schemas

AI may validate schema and evidence-ID existence only. All judgement values
below are entered by the researcher.

## A. Base-case record (`BASE_22_HUMAN_SIGNED.jsonl`)

One JSON object per line. Required keys:

| Field | Type / allowed values |
|---|---|
| `record_type` | `"BASE_22"` |
| `case_id` | must match a case in `QUEUE_MANIFEST.json` reviewer_view |
| `question_valid` | `VALID` · `AMBIGUOUS` · `INVALID` · `REVIEW_UNRESOLVED` |
| `answerability` | `ANSWERABLE` · `UNANSWERABLE` · `REVIEW_UNRESOLVED` |
| `sufficiency` | `SUPPORTED` · `PARTIAL` · `INSUFFICIENT` · `CONFLICTING` · `REFUTED` · `REVIEW_UNRESOLVED` |
| `entity` | string or `null` |
| `metric` | string or `null` |
| `target_period` | string (e.g. `FY2024`) or `null` |
| `unit_and_scale` | string (e.g. `USD, raw`) or `null` |
| `reporting_scope` | string (e.g. `consolidated`) or `null` |
| `mandatory_requirements` | array of requirement descriptors (strings) |
| `supporting_evidence_ids` | array of evidence IDs found sufficient |
| `minimal_evidence_set` | array of evidence IDs forming a minimal set |
| `source_time_valid` | `true` · `false` · `null` |
| `version_valid` | `true` · `false` · `null` |
| `calculation_reproducible` | `true` · `false` · `null` |
| `final_answer_or_null` | number, string, or `null` (ABSTAIN) |
| `reviewer_confidence` | `1`…`5` or `null` |
| `reviewer_notes` | string or `null` |
| `signed_by` | researcher identifier (signature) |
| `timestamp` | ISO-8601 UTC (signature) |
| `elapsed_seconds` | number |

Optional acknowledgment: `"signed": true`.

## B. Paired record (`PAIRED_12_HUMAN_SIGNED.jsonl`)

Same fields as §A with:

| Field | Value |
|---|---|
| `record_type` | `"PAIRED_12"` |
| `review_token` | `pr-01`…`pr-12` (from reviewer sheet) |
| `condition_identity` | `"HIDDEN_DURING_REVIEW"` (researcher does not fill) |
| `pass` | `1` |

`instance_id` is resolved after review via the sealed token map.

## C. Blind-repeat record (`BLIND_REPEAT_5.jsonl`)

Same fields as §A with:

| Field | Value |
|---|---|
| `record_type` | `"BLIND_REPEAT"` |
| `temp_id` | `br-01`…`br-05` |
| `pass` | `1` (first) or `2` (repeat, ≥4h later, without looking) |

The underlying `case_id` is joined after both passes freeze.

## D. Interface-pilot record (`INTERFACE_PILOT_9.jsonl`)

| Field | Type / allowed values |
|---|---|
| `record_type` | `"INTERFACE_PILOT"` |
| `case_id` | matches reviewer sheet |
| `display_condition` | `answer_only` · `answer_topk_pages` · `answer_vista_package` |
| `final_judgement` | `ACCEPT` · `ACCEPT_WITH_RESERVATIONS` · `REJECT` · `REVIEW_UNRESOLVED` |
| `error_detected` | `true` · `false` · `null` |
| `missing_evidence_detected` | `true` · `false` · `null` |
| `wrong_period_detected` | `true` · `false` · `null` |
| `review_time_seconds` | number |
| `confidence` | `1`…`5` |
| `interface_notes` | string |
| `signed_by`, `timestamp`, `elapsed_seconds` | as §A |

Section labels (top-level): `SINGLE_REVIEWER_USABILITY_PILOT`,
`NO_HUMAN_EFFECTIVENESS_CLAIM`.

## E. Validation rules (AI-enforced)

- `case_id` / `review_token` / `temp_id` must exist in the frozen manifest.
- A record counts as a **human label** only when `signed_by` is non-empty
  and `timestamp` is present.
- `REVIEW_UNRESOLVED` is valid on any categorical field; `null` is valid
  where the table says so. Nothing forces a confident answer.
