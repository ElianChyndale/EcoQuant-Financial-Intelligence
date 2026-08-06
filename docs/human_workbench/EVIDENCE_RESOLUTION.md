# Workbench Evidence Resolution

**Date:** 2026-08-06

## Purpose

The frozen manifest stores evidence descriptors (concept, document, filing
date, unit, scale, scope) but `text_span`/`table_id` are often null. The
workbench resolves the ORIGINAL local source material so the researcher reviews
real filings, not descriptors.

## Resolution order

1. **XBRL companyfacts** (`research/cache/sec/{issuer}_companyfacts.json`) —
   the most authoritative structured fact. Returns concept label, value, unit,
   start/end, form, filed, frame, source fact id.
2. **Full 10-K HTML** (`research/cache/sec/full_10k/`) — finds the concept (or
   its CamelCase-humanized form) in the document and returns a text excerpt.
3. **Explicit failure** — if neither source exists, returns
   `EVIDENCE_RESOLUTION_FAILED` with the exact missing asset. No fabricated
   fallback.

## Traceability fields

stable evidence ID · issuer · filing type · document ID · filing date ·
source cutoff · fiscal period · document version · amendment relationship ·
page/section · table ID · row/column · text span · XBRL concept · value ·
unit · scale · scope · local source identifier · content hash.

## Coverage

- Every one of the 22 base cases' evidence items is resolved or produces an
  explicit `EVIDENCE_RESOLUTION_FAILED` with the missing asset named
  (`test_workbench.py::test_all_22_base_cases_resolve_or_report_failure`).
- Missing source → explicit failure state, never fabricated
  (`test_missing_source_is_explicit_failure`).

## Unresolved evidence assets

The 6 full 10-K documents and 6 companyfacts files are in the local cache.
Evidence referencing a company/year whose source file is absent will report
`EVIDENCE_RESOLUTION_FAILED` honestly.
