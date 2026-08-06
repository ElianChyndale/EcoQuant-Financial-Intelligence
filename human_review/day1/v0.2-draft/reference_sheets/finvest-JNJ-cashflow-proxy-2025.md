# Reference Case (CANDIDATE): finvest-JNJ-cashflow-proxy-2025

**Status:** CANDIDATE_UNREVIEWED

## Question
What is JNJ operating cash flow minus capital expenditure for the fiscal period ending 2025-12-28?

**Term definition:** Definition of metric to be confirmed by the researcher.

**Answer type:** derived
**Source cutoff:** 2026-02-11 00:00:00
**Target period:** 2024-12-30 -> 2025-12-28

## Evidence
- `JNJ:us-gaap:NetCashProvidedByUsedInOperatingActivities:USD:2024-12-30:2025-12-28:10-K:0000200406-26-000016`: NetCashProvidedByUsedInOperatingActivities · USD · 2024-12-30 -> 2025-12-28 · filed 2026-02-11 · 10-K
- `JNJ:us-gaap:PaymentsToAcquirePropertyPlantAndEquipment:USD:2024-12-30:2025-12-28:10-K:0000200406-26-000016`: PaymentsToAcquirePropertyPlantAndEquipment · USD · 2024-12-30 -> 2025-12-28 · filed 2026-02-11 · 10-K

## Calculation
CalculationProgram(operation='subtract', inputs=('OperatingCashFlow', 'CapitalExpenditure'), result=19698000000.0, unit='USD', scale='1', period='FY2025')

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