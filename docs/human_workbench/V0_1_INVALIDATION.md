# Day-1 v0.1 Protocol Invalidation

**Date:** 2026-08-06
**Status:** INVALIDATED_BENCHMARK_CONSTRUCTION
**Immutable record — do not edit.** Preserve the original v0.1 artifacts and
hashes.

---

## Identity

| Field | Value |
|---|---|
| Protocol version | `day1-human-validation-pilot v0.1` |
| Manifest ID | `day1-human-validation-pilot` |
| Manifest version | `0.1.0` |
| Frozen at | `2026-08-06T03:11:33+00:00` |
| Total SHA-256 | `bb0f1e6a6f892fed40d7ba103bf8d5c0c4b5e2ddd47e746002d6328e60e3` |
| Commit (audit) | `ead62ecb83ea2a50d8d1fb8c9625929139213e97` |

## Affected builder function

`finvest/benchmark/builders/sec_cases.py::_amended_pair`

## Discovered failure

`_amended_pair` groups facts only by **period end + form**, not by taxonomy
concept. The `by_end.setdefault(end, {})[form] = fact` pattern means the last
fact of each form for a period wins, regardless of concept. This can pair a
10-K fact for one concept with a 10-K/A fact for a **different** concept, and
can produce an amendment that **predates** the original.

## Confirmed affected case

`finvest-AAPL-amended-SalesRevenueNet-2009-03-28`

- original: `SalesRevenueNet`, form `10-K`, filed `2010-10-27`
- "amended": `EntityPublicFloat`, form `10-K/A`, filed `2010-01-25`

The concepts differ (`SalesRevenueNet` vs `EntityPublicFloat`), and the
"amendment" (2010-01-25) predates the original (2010-10-27). This is a
scientifically invalid version relation.

## Classification

```
day1-human-validation-pilot v0.1 = INVALIDATED_BENCHMARK_CONSTRUCTION
```

Do not describe v0.1 as human-validated.

## Confirmation of zero human labels

- All four human-record JSONL files are empty (0 bytes).
- Zero human labels were created, inferred, signed, or corrected.
- No scientific result used these labels.

## Preserved artifacts (unchanged)

- `human_review/day1/QUEUE_MANIFEST.json` — original hashes preserved.
- `human_review/day1/FROZEN.sha256` — original hashes preserved.
- All four `*_HUMAN_SIGNED.jsonl` / `INTERFACE_PILOT_9.jsonl` / `BLIND_REPEAT_5.jsonl`
  files — empty and unchanged.
- `ANNOTATION_GUIDELINE.md`, `SCHEMA.md`, `REVIEWER_SHEET.md` — unchanged.

## Resolution

A versioned `day1 v0.2` protocol is created separately (see
`V0_2_CASE_AUDIT.md`). v0.1 content is preserved under its original identity;
v0.2 is a clean replacement, not a silent mutation of v0.1.
