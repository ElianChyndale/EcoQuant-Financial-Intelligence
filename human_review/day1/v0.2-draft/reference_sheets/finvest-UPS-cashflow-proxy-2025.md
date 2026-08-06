# Reference Case (CANDIDATE): finvest-UPS-cashflow-proxy-2025

**Status:** CANDIDATE_UNREVIEWED

## Question
What is UPS operating cash flow minus capital expenditure for the fiscal period ending 2025-12-31?

## Metric definition (explicit)
本题按以下显式定义计算：first input − second input (absolute value where the source reports a negative outflow)。输入项分别为 OperatingCashFlow 和 CapitalExpenditure。

**Assumptions:**
- SIMPLIFIED cash-flow proxy = OCF - capex; NOT standard FCFF (no tax/interest/working-capital adjustments).

## Original evidence table

| Row | Value | Unit | Period | Source (form · filed · accn) |
|---|---|---|---|---|
| Net cash provided by operating activities | 8,450,000,000 | USD | FY2025 | 10-K · 2026-02-17 · 0001628280-26-008432 |
| Payments for acquisition of property, plant and equipment | 3,685,000,000 | USD | FY2025 | 10-K · 2026-02-17 · 0001628280-26-008432 |

数值取自 SEC XBRL companyfacts（原始来源见时间版本卡）。

## Independent calculation (inputs only — recompute yourself)

**Operation:** first input − second input (absolute value where the source reports a negative outflow)
- Net cash provided by operating activities = 8,450,000,000 USD
- Payments for acquisition of property, plant and equipment = 3,685,000,000 USD
*请根据上方两个输入独立计算并填写结果；机器候选答案在提交前不会显示。*

## Time & version card

- Target period: FY2025
- Source cutoff: 2026-02-17 00:00:00
- Net cash provided by operating activities: 2025-01-01 → 2025-12-31 · filed 2026-02-17 (10-K) · accn 0001628280-26-008432 · after-target=是 · ORIGINAL
- Payments for acquisition of property, plant and equipment: 2025-01-01 → 2025-12-31 · filed 2026-02-17 (10-K) · accn 0001628280-26-008432 · after-target=是 · ORIGINAL
*若 filing date 晚于目标期结束日，需自行判断：后发 10-K 是否包含目标期 comparative figures，是否存在 amendment/restatement，以及是否应优先使用 更接近目标期的原始 filing。*

## Machine candidate (NOT the researcher's answer)
- Decision: **ANSWER** · Sufficiency: **SUPPORTED**
- 机器候选判定。研究者必须独立重算并与本候选对照后才能接受。


## Researcher review (candidate)
- [ ] I understand the question
- [ ] I found the original source
- [ ] I agree the metric definition
- [ ] I agree the period
- [ ] I agree the unit
- [ ] I recomputed the answer independently and it matches
- [ ] The minimal evidence is sufficient
- [ ] No ambiguity found

*Candidate sheet prepared by AI. Researcher approval required before use as gold.*