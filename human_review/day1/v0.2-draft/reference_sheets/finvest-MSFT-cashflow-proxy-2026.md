# Reference Case (CANDIDATE): finvest-MSFT-cashflow-proxy-2026

**Status:** CANDIDATE_UNREVIEWED

## Question
What is MSFT operating cash flow minus capital expenditure for the fiscal period ending 2026-06-30?

**Term definition:** Definition of metric to be confirmed by the researcher.

**Answer type:** derived
**Source cutoff:** 2026-07-29 00:00:00
**Target period:** 2025-07-01 -> 2026-06-30

## Evidence
- `MSFT:us-gaap:NetCashProvidedByUsedInOperatingActivities:USD:2025-07-01:2026-06-30:10-K:0001193125-26-323660`: NetCashProvidedByUsedInOperatingActivities · USD · 2025-07-01 -> 2026-06-30 · filed 2026-07-29 · 10-K
- `MSFT:us-gaap:PaymentsToAcquirePropertyPlantAndEquipment:USD:2025-07-01:2026-06-30:10-K:0001193125-26-323660`: PaymentsToAcquirePropertyPlantAndEquipment · USD · 2025-07-01 -> 2026-06-30 · filed 2026-07-29 · 10-K

## Calculation
CalculationProgram(operation='subtract', inputs=('OperatingCashFlow', 'CapitalExpenditure'), result=66987000000.0, unit='USD', scale='1', period='FY2026')

**Decision:** ANSWER · **Sufficiency:** SUPPORTED

## Researcher review (candidate)
- [ ] I understand the question
- [ ] I found the original source
- [ ] I agree the metric definition
- [ ] I agree the period
- [ ] I agree the unit
- [ ] I can recompute the answer
- [ ] The minimal evidence is sufficient
- [ ] No ambiguity found

*Candidate sheet prepared by AI. Researcher approval required before use as gold.*