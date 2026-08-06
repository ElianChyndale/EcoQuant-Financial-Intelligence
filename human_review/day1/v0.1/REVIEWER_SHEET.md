# Day-1 Reviewer Sheet (display-safe)

Annotation surface for the day-1 pilot. Candidate answers, system
scores, gold labels, and condition identities are NOT shown here.
See ANNOTATION_GUIDELINE.md before starting.

## 22 base cases (first pass)

| Case ID | Question | Evidence (id · document · concept · period) |
|---|---|---|
| finvest-AAPL-amended-SalesRevenueNet-2009-03-28 | What is the latest restated value of SalesRevenueNet for AAPL for the period ending 2009-03-28? | AAPL:SalesRevenueNet:2009-03-28:2010-10-27:10-K · AAPL-10-K-2009-03-28 · SalesRevenueNet · 2009-03-28; AAPL:EntityPublicFloat:2009-03-28:2010-01-25:10-K/A · AAPL-10-K/A-2009-03-28 · EntityPublicFloat · 2009-03-28 |
| finvest-AAPL-fcff-2024 | What is AAPL free cash flow to the firm for fiscal year 2024? | AAPL:NetCashProvidedByUsedInOperatingActivities:2024-09-28:2025-10-31:10-K · AAPL-10-K-2024-09-28 · NetCashProvidedByUsedInOperatingActivities · 2024-09-28; AAPL:PaymentsToAcquirePropertyPlantAndEquipment:2024-09-28:2025-10-31:10-K · AAPL-10-K-2024-09-28 · PaymentsToAcquirePropertyPlantAndEquipment · 2024-09-28 |
| finvest-AAPL-fcff-2025 | What is AAPL free cash flow to the firm for fiscal year 2025? | AAPL:NetCashProvidedByUsedInOperatingActivities:2025-09-27:2025-10-31:10-K · AAPL-10-K-2025-09-27 · NetCashProvidedByUsedInOperatingActivities · 2025-09-27; AAPL:PaymentsToAcquirePropertyPlantAndEquipment:2025-09-27:2025-10-31:10-K · AAPL-10-K-2025-09-27 · PaymentsToAcquirePropertyPlantAndEquipment · 2025-09-27 |
| finvest-AAPL-insufficient-AccruedIncomeTaxesNoncurrent-2025 | What is AccruedIncomeTaxesNoncurrent for AAPL for fiscal year 2025? | (no evidence descriptor provided — verify against SEC source) |
| finvest-AAPL-insufficient-AccruedLiabilitiesCurrent-2024 | What is AccruedLiabilitiesCurrent for AAPL for fiscal year 2024? | (no evidence descriptor provided — verify against SEC source) |
| finvest-EQIX-amended-DividendsCommonStockStock-2022-06-30 | What is the latest restated value of DividendsCommonStockStock for EQIX for the period ending 2022-06-30? | EQIX:DividendsCommonStockStock:2022-06-30:2025-02-12:10-K · EQIX-10-K-2022-06-30 · DividendsCommonStockStock · 2022-06-30; EQIX:EntityPublicFloat:2022-06-30:2023-02-27:10-K/A · EQIX-10-K/A-2022-06-30 · EntityPublicFloat · 2022-06-30 |
| finvest-EQIX-insufficient-AccountsPayableAndAccruedLiabilitiesCurrent-2026 | What is AccountsPayableAndAccruedLiabilitiesCurrent for EQIX for fiscal year 2026? | (no evidence descriptor provided — verify against SEC source) |
| finvest-EQIX-insufficient-AccountsPayableRelatedPartiesCurrentAndNoncurrent-2025 | What is AccountsPayableRelatedPartiesCurrentAndNoncurrent for EQIX for fiscal year 2025? | (no evidence descriptor provided — verify against SEC source) |
| finvest-JNJ-fcff-2025 | What is JNJ free cash flow to the firm for fiscal year 2025? | JNJ:NetCashProvidedByUsedInOperatingActivities:2025-12-28:2026-02-11:10-K · JNJ-10-K-2025-12-28 · NetCashProvidedByUsedInOperatingActivities · 2025-12-28; JNJ:PaymentsToAcquirePropertyPlantAndEquipment:2025-12-28:2026-02-11:10-K · JNJ-10-K-2025-12-28 · PaymentsToAcquirePropertyPlantAndEquipment · 2025-12-28 |
| finvest-JNJ-insufficient-AcceleratedShareRepurchasesSettlementPaymentOrReceipt-2025 | What is AcceleratedShareRepurchasesSettlementPaymentOrReceipt for JNJ for fiscal year 2025? | (no evidence descriptor provided — verify against SEC source) |
| finvest-JNJ-insufficient-AcceleratedShareRepurchasesSettlementPaymentOrReceipt-2026 | What is AcceleratedShareRepurchasesSettlementPaymentOrReceipt for JNJ for fiscal year 2026? | (no evidence descriptor provided — verify against SEC source) |
| finvest-KO-fcff-2025 | What is KO free cash flow to the firm for fiscal year 2025? | KO:NetCashProvidedByUsedInOperatingActivities:2025-12-31:2026-02-20:10-K · KO-10-K-2025-12-31 · NetCashProvidedByUsedInOperatingActivities · 2025-12-31; KO:PaymentsToAcquirePropertyPlantAndEquipment:2025-12-31:2026-02-20:10-K · KO-10-K-2025-12-31 · PaymentsToAcquirePropertyPlantAndEquipment · 2025-12-31 |
| finvest-KO-insufficient-AccountsPayableAndAccruedLiabilitiesCurrent-2026 | What is AccountsPayableAndAccruedLiabilitiesCurrent for KO for fiscal year 2026? | (no evidence descriptor provided — verify against SEC source) |
| finvest-KO-insufficient-AccountsPayableOtherCurrent-2025 | What is AccountsPayableOtherCurrent for KO for fiscal year 2025? | (no evidence descriptor provided — verify against SEC source) |
| finvest-MSFT-fcff-2025 | What is MSFT free cash flow to the firm for fiscal year 2025? | MSFT:NetCashProvidedByUsedInOperatingActivities:2025-06-30:2026-07-29:10-K · MSFT-10-K-2025-06-30 · NetCashProvidedByUsedInOperatingActivities · 2025-06-30; MSFT:PaymentsToAcquirePropertyPlantAndEquipment:2025-06-30:2026-07-29:10-K · MSFT-10-K-2025-06-30 · PaymentsToAcquirePropertyPlantAndEquipment · 2025-06-30 |
| finvest-MSFT-fcff-2026 | What is MSFT free cash flow to the firm for fiscal year 2026? | MSFT:NetCashProvidedByUsedInOperatingActivities:2026-06-30:2026-07-29:10-K · MSFT-10-K-2026-06-30 · NetCashProvidedByUsedInOperatingActivities · 2026-06-30; MSFT:PaymentsToAcquirePropertyPlantAndEquipment:2026-06-30:2026-07-29:10-K · MSFT-10-K-2026-06-30 · PaymentsToAcquirePropertyPlantAndEquipment · 2026-06-30 |
| finvest-MSFT-insufficient-AccountsReceivableNet-2025 | What is AccountsReceivableNet for MSFT for fiscal year 2025? | (no evidence descriptor provided — verify against SEC source) |
| finvest-MSFT-insufficient-AccountsReceivableNet-2026 | What is AccountsReceivableNet for MSFT for fiscal year 2026? | (no evidence descriptor provided — verify against SEC source) |
| finvest-UPS-fcff-2024 | What is UPS free cash flow to the firm for fiscal year 2024? | UPS:NetCashProvidedByUsedInOperatingActivities:2024-12-31:2026-02-17:10-K · UPS-10-K-2024-12-31 · NetCashProvidedByUsedInOperatingActivities · 2024-12-31; UPS:PaymentsToAcquirePropertyPlantAndEquipment:2024-12-31:2026-02-17:10-K · UPS-10-K-2024-12-31 · PaymentsToAcquirePropertyPlantAndEquipment · 2024-12-31 |
| finvest-UPS-fcff-2025 | What is UPS free cash flow to the firm for fiscal year 2025? | UPS:NetCashProvidedByUsedInOperatingActivities:2025-12-31:2026-02-17:10-K · UPS-10-K-2025-12-31 · NetCashProvidedByUsedInOperatingActivities · 2025-12-31; UPS:PaymentsToAcquirePropertyPlantAndEquipment:2025-12-31:2026-02-17:10-K · UPS-10-K-2025-12-31 · PaymentsToAcquirePropertyPlantAndEquipment · 2025-12-31 |
| finvest-UPS-insufficient-AccountsReceivableGrossCurrent-2025 | What is AccountsReceivableGrossCurrent for UPS for fiscal year 2025? | (no evidence descriptor provided — verify against SEC source) |
| finvest-UPS-insufficient-AccruedIncomeTaxesCurrent-2024 | What is AccruedIncomeTaxesCurrent for UPS for fiscal year 2024? | (no evidence descriptor provided — verify against SEC source) |

## 12 paired cases (condition identity hidden)

| Token | Question | Evidence (id · document · concept · period) |
|---|---|---|
| pr-01 | What is KO free cash flow to the firm for fiscal year 2025? | KO:NetCashProvidedByUsedInOperatingActivities:2025-12-31:2026-02-20:10-K · KO-10-K-2025-12-31 · NetCashProvidedByUsedInOperatingActivities · 2025-12-31 |
| pr-02 | What is MSFT free cash flow to the firm for fiscal year 2025? | MSFT:NetCashProvidedByUsedInOperatingActivities:2025-06-30:2026-07-29:10-K · MSFT-10-K-2025-06-30 · NetCashProvidedByUsedInOperatingActivities · 2025-06-30; MSFT:PaymentsToAcquirePropertyPlantAndEquipment:2025-06-30:2026-07-29:10-K · MSFT-10-K-2025-06-30 · PaymentsToAcquirePropertyPlantAndEquipment · 2025-06-30; AAPL:EntityPublicFloat:2009-03-28:2010-01-25:10-K/A.x · AAPL-10-K/A-2009-03-28 · EntityPublicFloat · 2009-03-28 |
| pr-03 | What is AAPL free cash flow to the firm for fiscal year 2024? | AAPL:NetCashProvidedByUsedInOperatingActivities:2024-09-28:2025-10-31:10-K · AAPL-10-K-2024-09-28 · NetCashProvidedByUsedInOperatingActivities · 2024-09-28; AAPL:PaymentsToAcquirePropertyPlantAndEquipment:2024-09-28:2025-10-31:10-K · AAPL-10-K-2024-09-28 · PaymentsToAcquirePropertyPlantAndEquipment · 2024-09-28; AAPL:NetCashProvidedByUsedInOperatingActivities:2024-09-28:2025-10-31:10-K-amended · AAPL-10-K-2024-09-28 · NetCashProvidedByUsedInOperatingActivities · 2024-09-28 |
| pr-04 | What is JNJ free cash flow to the firm for fiscal year 2025? | JNJ:NetCashProvidedByUsedInOperatingActivities:2025-12-28:2026-02-11:10-K · JNJ-10-K-2025-12-28 · NetCashProvidedByUsedInOperatingActivities · 2025-12-28 |
| pr-05 | What is MSFT free cash flow to the firm for fiscal year 2025? | MSFT:NetCashProvidedByUsedInOperatingActivities:2025-06-30:2026-07-29:10-K · MSFT-10-K-2025-06-30 · NetCashProvidedByUsedInOperatingActivities · 2025-06-30 |
| pr-06 | What is UPS free cash flow to the firm for fiscal year 2025? | AAPL:EntityPublicFloat:2009-03-28:2010-01-25:10-K/A.x · AAPL-10-K/A-2009-03-28 · EntityPublicFloat · 2009-03-28; AAPL:NetCashProvidedByUsedInOperatingActivities:2024-09-28:2025-10-31:10-K · AAPL-10-K-2024-09-28 · NetCashProvidedByUsedInOperatingActivities · 2024-09-28; UPS:NetCashProvidedByUsedInOperatingActivities:2025-12-31:2026-02-17:10-K · UPS-10-K-2025-12-31 · NetCashProvidedByUsedInOperatingActivities · 2025-12-31; UPS:PaymentsToAcquirePropertyPlantAndEquipment:2025-12-31:2026-02-17:10-K · UPS-10-K-2025-12-31 · PaymentsToAcquirePropertyPlantAndEquipment · 2025-12-31 |
| pr-07 | What is the latest restated value of SalesRevenueNet for AAPL for the period ending 2009-03-28? | AAPL:NetCashProvidedByUsedInOperatingActivities:2024-09-28:2025-10-31:10-K.x · AAPL-10-K-2024-09-28 · NetCashProvidedByUsedInOperatingActivities · 2024-09-28; AAPL:NetCashProvidedByUsedInOperatingActivities:2025-09-27:2025-10-31:10-K · AAPL-10-K-2025-09-27 · NetCashProvidedByUsedInOperatingActivities · 2025-09-27; AAPL:SalesRevenueNet:2009-03-28:2010-10-27:10-K · AAPL-10-K-2009-03-28 · SalesRevenueNet · 2009-03-28; AAPL:EntityPublicFloat:2009-03-28:2010-01-25:10-K/A · AAPL-10-K/A-2009-03-28 · EntityPublicFloat · 2009-03-28 |
| pr-08 | What is MSFT free cash flow to the firm for fiscal year 2025? | MSFT:NetCashProvidedByUsedInOperatingActivities:2025-06-30:2026-07-29:10-K · MSFT-10-K-2025-06-30 · NetCashProvidedByUsedInOperatingActivities · 2024-06-30; MSFT:PaymentsToAcquirePropertyPlantAndEquipment:2025-06-30:2026-07-29:10-K · MSFT-10-K-2025-06-30 · PaymentsToAcquirePropertyPlantAndEquipment · 2024-06-30 |
| pr-09 | What is KO free cash flow to the firm for fiscal year 2025? | KO:NetCashProvidedByUsedInOperatingActivities:2025-12-31:2026-02-20:10-K · KO-10-K-2025-12-31 · NetCashProvidedByUsedInOperatingActivities · 2025-12-31 |
| pr-10 | What is KO free cash flow to the firm for fiscal year 2025? | KO:NetCashProvidedByUsedInOperatingActivities:2025-12-31:2026-02-20:10-K · KO-10-K-2025-12-31 · NetCashProvidedByUsedInOperatingActivities · 2024-12-31; KO:PaymentsToAcquirePropertyPlantAndEquipment:2025-12-31:2026-02-20:10-K · KO-10-K-2025-12-31 · PaymentsToAcquirePropertyPlantAndEquipment · 2024-12-31 |
| pr-11 | What is MSFT free cash flow to the firm for fiscal year 2026? | MSFT:NetCashProvidedByUsedInOperatingActivities:2026-06-30:2026-07-29:10-K · MSFT-10-K-2026-06-30 · NetCashProvidedByUsedInOperatingActivities · 2026-06-30; MSFT:PaymentsToAcquirePropertyPlantAndEquipment:2026-06-30:2026-07-29:10-K · MSFT-10-K-2026-06-30 · PaymentsToAcquirePropertyPlantAndEquipment · 2026-06-30; AAPL:EntityPublicFloat:2009-03-28:2010-01-25:10-K/A.x · AAPL-10-K/A-2009-03-28 · EntityPublicFloat · 2009-03-28 |
| pr-12 | What is the latest restated value of SalesRevenueNet for AAPL for the period ending 2009-03-28? | AAPL:SalesRevenueNet:2009-03-28:2010-10-27:10-K · AAPL-10-K-2009-03-28 · SalesRevenueNet · 2009-03-28; AAPL:EntityPublicFloat:2009-03-28:2010-01-25:10-K/A · AAPL-10-K/A-2009-03-28 · EntityPublicFloat · 2009-03-28; AAPL:SalesRevenueNet:2009-03-28:2010-10-27:10-K-amended · AAPL-10-K-2009-03-28 · SalesRevenueNet · 2009-03-28 |

## 5 blind repeats (second pass, temp IDs)

| Temp ID | Question |
|---|---|
| br-01 | What is UPS free cash flow to the firm for fiscal year 2025? |
| br-02 | What is KO free cash flow to the firm for fiscal year 2025? |
| br-03 | What is AccountsPayableOtherCurrent for KO for fiscal year 2025? |
| br-04 | What is JNJ free cash flow to the firm for fiscal year 2025? |
| br-05 | What is the latest restated value of SalesRevenueNet for AAPL for the period ending 2009-03-28? |

## 9 interface-pilot cases (display condition IS shown)

| Case ID | Display condition | Question |
|---|---|---|
| finvest-KO-fcff-2025 | answer_only | What is KO free cash flow to the firm for fiscal year 2025? |
| finvest-MSFT-fcff-2026 | answer_topk_pages | What is MSFT free cash flow to the firm for fiscal year 2026? |
| finvest-AAPL-amended-SalesRevenueNet-2009-03-28 | answer_vista_package | What is the latest restated value of SalesRevenueNet for AAPL for the period ending 2009-03-28? |
| finvest-UPS-insufficient-AccruedIncomeTaxesCurrent-2024 | answer_topk_pages | What is AccruedIncomeTaxesCurrent for UPS for fiscal year 2024? |
| finvest-KO-insufficient-AccountsPayableOtherCurrent-2025 | answer_only | What is AccountsPayableOtherCurrent for KO for fiscal year 2025? |
| finvest-AAPL-fcff-2024 | answer_vista_package | What is AAPL free cash flow to the firm for fiscal year 2024? |
| finvest-JNJ-insufficient-AcceleratedShareRepurchasesSettlementPaymentOrReceipt-2026 | answer_only | What is AcceleratedShareRepurchasesSettlementPaymentOrReceipt for JNJ for fiscal year 2026? |
| finvest-AAPL-insufficient-AccruedIncomeTaxesNoncurrent-2025 | answer_topk_pages | What is AccruedIncomeTaxesNoncurrent for AAPL for fiscal year 2025? |
| finvest-MSFT-insufficient-AccountsReceivableNet-2025 | answer_vista_package | What is AccountsReceivableNet for MSFT for fiscal year 2025? |
