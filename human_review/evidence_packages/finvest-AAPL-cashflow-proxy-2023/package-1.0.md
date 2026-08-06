# Case: finvest-AAPL-cashflow-proxy-2023

**问题**：What is AAPL operating cash flow minus capital expenditure for the fiscal period ending 2023-09-30?

## 指标定义（显式）
本题按以下显式定义计算：first input − second input (absolute value where the source reports a negative outflow)。输入项分别为 OperatingCashFlow 和 CapitalExpenditure。
- 假设：SIMPLIFIED cash-flow proxy = OCF - capex; NOT standard FCFF (no tax/interest/working-capital adjustments).

## ① 原始 SEC 数据行（验证门禁——逐字来源，可独立核对）

```json
[
  {
    "concept": "NetCashProvidedByUsedInOperatingActivities",
    "taxonomy": "us-gaap",
    "val": 110543000000.0,
    "unit": "USD",
    "start": "2022-09-25",
    "end": "2023-09-30",
    "fy": "2023",
    "fp": "FY",
    "form": "10-K",
    "filed": "2023-11-03",
    "accn": "0000320193-23-000106",
    "source_file": "research/cache/sec/aapl_companyfacts.json",
    "source_hash": "8c1168a39f3f23a8f43a7c216c2e8ada09fca3e2ac16962259bd4bc3aebd6f17"
  },
  {
    "concept": "PaymentsToAcquirePropertyPlantAndEquipment",
    "taxonomy": "us-gaap",
    "val": 10959000000.0,
    "unit": "USD",
    "start": "2022-09-25",
    "end": "2023-09-30",
    "fy": "2023",
    "fp": "FY",
    "form": "10-K",
    "filed": "2023-11-03",
    "accn": "0000320193-23-000106",
    "source_file": "research/cache/sec/aapl_companyfacts.json",
    "source_hash": "103ca7b4a48d8c6133ab6d0f41bda89ac06f31cae38372628460911d3818c5f6"
  }
]
```
来源文件: research/cache/sec/aapl_companyfacts.json · sha256: 8c1168a39f3f23a8…

## ② 人类可读解读

- **Net cash provided by operating activities**: 110,543,000,000 USD · FY2023 · 10-K · filed 2023-11-03 · accn 0000320193-23-000106
- **Payments for acquisition of property, plant and equipment**: 10,959,000,000 USD · FY2023 · 10-K · filed 2023-11-03 · accn 0000320193-23-000106

## ③ 独立计算区（输入已分开，请自行计算）
**运算**：first input − second input (absolute value where the source reports a negative outflow)
- Net cash provided by operating activities = 110,543,000,000 USD
- Payments for acquisition of property, plant and equipment = 10,959,000,000 USD
*请根据上方两个输入独立计算并填写结果；机器候选答案在提交前不会显示。*

## ④ 时间与版本卡
- 目标期: FY2023 · source cutoff: 2023-11-03 00:00:00
- Net cash provided by operating activities: 2022-09-25 → 2023-09-30 · filed 2023-11-03 (10-K) · accn 0000320193-23-000106 · 晚于目标期=是
- Payments for acquisition of property, plant and equipment: 2022-09-25 → 2023-09-30 · filed 2023-11-03 (10-K) · accn 0000320193-23-000106 · 晚于目标期=是
*若 filing date 晚于目标期结束日，需自行判断：后发 10-K 是否包含目标期 comparative figures，是否存在 amendment/restatement，以及是否应优先使用 更接近目标期的原始 filing。*

## ⑤ Q4 判断对照表（每类检查：现状 + 你该看什么）

| 检查项 | 页面当前状态 | 若下列为真则勾选 |
|---|---|---|
| **Wrong period** | 目标期 FY2023；证据期间 Net cash provided by operating activities: 2022-09-25 → 2023-09-30；Payments for acquisition of property, plant and equipment: 2022-09-25 → 2023-09-30 | 证据期间 ≠ 目标期间 |
| **Future source** | filing 日期 晚于期间结束 (2023-11-03, 2023-11-03)；cutoff 2023-11-03 00:00:00 | filing 晚于 cutoff 或无法确认期间归属 |
| **Version/amendment unclear** | form 10-K；amendment 未检出 | 存在 amendment/restatement 或版本关系不明 |
| **Metric definition unclear** | 定义 已显式声明 | 定义未定稿或概念映射(问题词汇→概念)不成立 |
| **Unit/scale unclear** | 单位 — | 单位不一致或与问题要求不符 |
| **Wrong entity** | issuer — | issuer ≠ 问题主体 |
| **Calculation mismatch** | 机器计算已隐藏(提交后核验)；输入见③ | 你的计算与机器结果不一致(核验阶段才可知) |
| **Missing evidence** | 已解析证据 2 行；计算输入 2 个 | 计算所需输入缺行 |
| **No issue found** | — | 以上各项均无异常 |

**请回答 Q1-Q5 + 置信度。**