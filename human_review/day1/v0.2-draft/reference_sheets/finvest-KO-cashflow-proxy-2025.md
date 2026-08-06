# Reference Case (CANDIDATE): finvest-KO-cashflow-proxy-2025

**Status:** CANDIDATE_UNREVIEWED

## Question
What is KO operating cash flow minus capital expenditure for the fiscal period ending 2025-12-31?

**Term definition:** Definition of metric to be confirmed by the researcher.

**Answer type:** derived
**Source cutoff:** 2026-02-20 00:00:00
**Target period:** 2025-01-01 -> 2025-12-31

## Evidence
- `KO:us-gaap:NetCashProvidedByUsedInOperatingActivities:USD:2025-01-01:2025-12-31:10-K:0001628280-26-010047`: NetCashProvidedByUsedInOperatingActivities · USD · 2025-01-01 -> 2025-12-31 · filed 2026-02-20 · 10-K
- `KO:us-gaap:PaymentsToAcquirePropertyPlantAndEquipment:USD:2025-01-01:2025-12-31:10-K:0001628280-26-010047`: PaymentsToAcquirePropertyPlantAndEquipment · USD · 2025-01-01 -> 2025-12-31 · filed 2026-02-20 · 10-K

## Calculation
CalculationProgram(operation='subtract', inputs=('OperatingCashFlow', 'CapitalExpenditure'), result=5296000000.0, unit='USD', scale='1', period='FY2025')

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