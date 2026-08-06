# Reference Case (CANDIDATE): finvest-AAPL-cashflow-proxy-2024

**Status:** CANDIDATE_UNREVIEWED

## Question
What is AAPL operating cash flow minus capital expenditure for the fiscal period ending 2024-09-28?

## Metric definition (explicit)
本题按以下显式定义计算：first input − second input (absolute value where the source reports a negative outflow)。输入项分别为 OperatingCashFlow 和 CapitalExpenditure。

**Assumptions:**
- SIMPLIFIED cash-flow proxy = OCF - capex; NOT standard FCFF (no tax/interest/working-capital adjustments).

## Original evidence table

| Row | Value | Unit | Period | Source (form · filed · accn) |
|---|---|---|---|---|
| Net cash provided by operating activities | 118,254,000,000 | USD | FY2024 | 10-K · 2024-11-01 · 0000320193-24-000123 |
| Payments for acquisition of property, plant and equipment | 9,447,000,000 | USD | FY2024 | 10-K · 2024-11-01 · 0000320193-24-000123 |

数值取自 SEC XBRL companyfacts（原始来源见时间版本卡）。

## Independent calculation (inputs only — recompute yourself)

**Operation:** first input − second input (absolute value where the source reports a negative outflow)
- Net cash provided by operating activities = 118,254,000,000 USD
- Payments for acquisition of property, plant and equipment = 9,447,000,000 USD
*请根据上方两个输入独立计算并填写结果；机器候选答案在提交前不会显示。*

## Time & version card

- Target period: FY2024
- Source cutoff: 2024-11-01 00:00:00
- Net cash provided by operating activities: 2023-10-01 → 2024-09-28 · filed 2024-11-01 (10-K) · accn 0000320193-24-000123 · after-target=是 · ORIGINAL
- Payments for acquisition of property, plant and equipment: 2023-10-01 → 2024-09-28 · filed 2024-11-01 (10-K) · accn 0000320193-24-000123 · after-target=是 · ORIGINAL
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