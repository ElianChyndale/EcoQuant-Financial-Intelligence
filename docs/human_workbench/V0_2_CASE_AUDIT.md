# Day-1 v0.2 Case Audit

**Date:** 2026-08-06
**Status:** AUDIT COMPLETE — v0.2 builder verified; no cross-concept amendment
pairs; version relations pass identity + chronology checks.

## Builder root cause (v0.1 defect)

`_amended_pair` grouped facts only by `(end, form)` and used last-wins
assignment. This paired a 10-K fact for one concept with a 10-K/A fact for a
different concept, and could produce an amendment predating the original.

**Confirmed v0.1 case:** `finvest-AAPL-amended-SalesRevenueNet-2009-03-28`
paired `SalesRevenueNet` (10-K, 2010-10-27) with `EntityPublicFloat` (10-K/A,
2010-01-25) — cross-concept AND the "amendment" predates the original.

## v0.2 fix

`_amended_pair` now groups by canonical identity
`(ticker, concept, end, unit)` and requires:
- same concept, same period end, same unit;
- original form `10-K`, amended form `10-K/A`;
- amended filed **on or after** original filed;
- values differ.

## v0.2 base queue (21 cases)

| Case | Answer type | Sufficiency | Version relation valid |
|---|---|---|---|
| finvest-AAPL-fcff-2024 | derived | SUPPORTED | n/a |
| finvest-AAPL-fcff-2025 | derived | SUPPORTED | n/a |
| finvest-AAPL-amended-AccruedLiabilitiesCurrent-2008-09-27 | extractive | CONFLICTING | **same concept, valid chronology** |
| finvest-MSFT-fcff-2025 | derived | SUPPORTED | n/a |
| finvest-MSFT-fcff-2026 | derived | SUPPORTED | n/a |
| finvest-KO-fcff-2025 | derived | SUPPORTED | n/a |
| finvest-JNJ-fcff-2025 | derived | SUPPORTED | n/a |
| finvest-UPS-fcff-2024 | derived | SUPPORTED | n/a |
| finvest-UPS-fcff-2025 | derived | SUPPORTED | n/a |
| 12× `*-insufficient-*` | unanswerable | INSUFFICIENT | n/a (no evidence, ABSTAIN) |

## Verification performed

1. **Every version relation**: same concept (`test_v02_amendment_integrity.py`),
   same period, 10-K→10-K/A, amended ≥ original, values differ. All pass.
2. **No cross-concept pair in the built queue**: regression test passes.
3. **Derived cases**: all have calculation programs.
4. **Insufficient cases**: genuinely unsupported (no evidence items) at the
   frozen cutoff → ABSTAIN.
5. **Preflight**: READY/TOOLING_BLOCKED/INVALID classification is deterministic
   and reproducible.

## Residual note

- 12 of 21 cases are `insufficient` (unanswerable) by construction — they are
  honest ABSTAIN cases, not annotation failures.
- The 8 fcff cases are the primary READY-for-annotation set (canonical evidence
  resolves for them).
- The 1 amended case has a valid same-concept version relation.

## v0.1 vs v0.2

- v0.1: 22 cases, 2 with invalid (cross-concept) version relations →
  **INVALIDATED_BENCHMARK_CONSTRUCTION**.
- v0.2: 21 cases, 1 valid version relation, no cross-concept defect.
- v0.1 hashes and artifacts preserved unchanged under their original identity.
