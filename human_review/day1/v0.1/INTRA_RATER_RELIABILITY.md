# Intra-Rater Reliability — Day-1 Pilot

**Status:** NO_DATA — the 5 blind-repeat second passes have not been
completed. This document fixes the methodology; numbers appear only after
both passes are frozen and signed.

## Design (frozen)

- 5 cases selected deterministically (seed 20260806) from the 22 base cases.
- Second pass uses temporary IDs (`br-01`…`br-05`), shuffled order, hidden
  prior labels, ≥ 4h gap recommended.
- Pass records join by `temp_id`; a pair exists only when both `pass: 1` and
  `pass: 2` are present and signed.

## Metrics (descriptive only)

| Metric | Definition |
|---|---|
| Categorical agreement | fraction of identical `final_answer_or_null` strings across the 5 pairs |
| Cohen's kappa | computed on the same pairs, **with small-sample warning**: n=5 < 30 ⇒ unstable; report descriptive agreement alongside; **no significance claim** |
| Evidence-set Jaccard | mean pairwise `|A ∩ B| / |A ∪ B|` over `supporting_evidence_ids` |
| Entity agreement | fraction of identical `entity` values |
| Period agreement | fraction of identical `target_period` values |
| Unit agreement | fraction of identical `unit_and_scale` values |
| Numeric agreement | both null ⇒ agree; one null ⇒ disagree; else relative tolerance 1e-6 |

## Constraints

- Labels are never revised to increase agreement.
- No inter-rater statistic of any kind: single reviewer.
- Output is produced by `python -m experiments.a9_human.run_day1
  reliability` and recorded here verbatim.

## Results

_(to be appended by the researcher after both passes freeze)_
