# Workbench Scientific Boundaries

**Date:** 2026-08-06

## The system does

FIND · ORGANISE · RENDER · COMPARE · NORMALISE · CALCULATE · VALIDATE · SAVE · TRACK

## The human does

UNDERSTAND · JUDGE · SELECT · EXPLAIN · SIGN

## Never

- infer, recommend, or display candidate labels, model predictions, scores, or
  prior annotations in first-pass flows;
- auto-sign a record;
- change frozen queues, QUEUE_MANIFEST.json, or hashes;
- write reviewer notes;
- silently fill a missing field;
- replace original evidence with a generated summary;
- convert interaction logs into labels.

## Evidence resolution

For every evidence item the app resolves ORIGINAL local source material
(text/table/XBRL from the SEC cache). If it cannot:

- displays `EVIDENCE_RESOLUTION_FAILED`;
- names the exact missing asset;
- allows `REVIEW_UNRESOLVED`;
- never fabricates replacement evidence;
- never silently falls back to generated text.

## Derived display

Optional, clearly labelled `DERIVED DISPLAY — NOT ORIGINAL EVIDENCE`. Contains
only deterministic transformations (normalized label/period/currency/scale,
unit conversion, duplicate grouping, arithmetic, version timeline, period
comparison). Every derived value links back to original evidence items.

## Neutral mechanical checks

Descriptive facts only. Allowed: "Evidence E02 was filed 37 days after the
source cutoff", "E01 and E03 use different fiscal periods", "The arithmetic
result from the displayed inputs is 74.071 billion".

Forbidden: "Choose ABSTAIN", "This case is OUTDATED", "The correct answer
is...", "Use E01 and E03", "The evidence is sufficient", "The system should
REVIEW".

## Base mode hides completely

candidate answer, generated sufficiency, generated route, model prediction,
model score, baseline correctness, gold labels, prior human annotation,
downstream VISTA result.

## Blind mode

- waits the frozen 4-hour period after all 22 base labels;
- uses temporary case IDs;
- hides all pass-1 fields server-side (not just frontend);
- prevents API routes from returning pass-1 fields.

## Interface mode

Server-side A/B/C information boundaries. Condition A shows only answer-only;
B shows answer + top-k evidence; C shows the structured evidence package.
Context/version tools are disabled for A and B server-side.
