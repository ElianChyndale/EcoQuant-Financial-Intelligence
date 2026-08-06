# Reference Case (CANDIDATE): finvest-AAPL-cashflow-proxy-2025

**Status:** CANDIDATE_UNREVIEWED

## Question
What is AAPL operating cash flow minus capital expenditure for the fiscal period ending 2025-09-27?

**Term definition:** Definition of metric to be confirmed by the researcher.

**Answer type:** derived
**Source cutoff:** 2025-10-31 00:00:00
**Target period:** 2024-09-29 -> 2025-09-27

## Evidence
- `AAPL:us-gaap:NetCashProvidedByUsedInOperatingActivities:USD:2024-09-29:2025-09-27:10-K:0000320193-25-000079`: NetCashProvidedByUsedInOperatingActivities · USD · 2024-09-29 -> 2025-09-27 · filed 2025-10-31 · 10-K
- `AAPL:us-gaap:PaymentsToAcquirePropertyPlantAndEquipment:USD:2024-09-29:2025-09-27:10-K:0000320193-25-000079`: PaymentsToAcquirePropertyPlantAndEquipment · USD · 2024-09-29 -> 2025-09-27 · filed 2025-10-31 · 10-K

## Calculation
CalculationProgram(operation='subtract', inputs=('OperatingCashFlow', 'CapitalExpenditure'), result=98767000000.0, unit='USD', scale='1', period='FY2025')

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