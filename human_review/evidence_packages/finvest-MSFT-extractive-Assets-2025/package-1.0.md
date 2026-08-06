# Case: finvest-MSFT-extractive-Assets-2025

**问题**：What is Assets for MSFT for fiscal year 2025?

## 指标定义（显式）
本题为直接提取/事实性问题；请按页面证据表与时间版本卡判断。

## ① 原始 SEC 数据行（验证门禁——逐字来源，可独立核对）

```json
[
  {
    "concept": "Assets",
    "taxonomy": "us-gaap",
    "val": 619003000000.0,
    "unit": "USD",
    "start": "",
    "end": "2025-06-30",
    "fy": "2025",
    "fp": "FY",
    "form": "10-K",
    "filed": "2025-07-30",
    "accn": "0000950170-25-100235",
    "source_file": "research/cache/sec/msft_companyfacts.json",
    "source_hash": "a473015cf7f5cc8ab4800e4b975396116ce87d913ff3d8864bbe2f11078e6907"
  }
]
```
来源文件: research/cache/sec/msft_companyfacts.json · sha256: a473015cf7f5cc8a…

## ② 人类可读解读

- **Total assets**: 619,003,000,000 USD · FY2025 · 10-K · filed 2025-07-30 · accn 0000950170-25-100235

## ④ 时间与版本卡
- 目标期: FY2025 · source cutoff: 2025-07-30 00:00:00
- Total assets: — → 2025-06-30 · filed 2025-07-30 (10-K) · accn 0000950170-25-100235 · 晚于目标期=是
*若 filing date 晚于目标期结束日，需自行判断：后发 10-K 是否包含目标期 comparative figures，是否存在 amendment/restatement，以及是否应优先使用 更接近目标期的原始 filing。*

## ⑤ Q4 判断对照表（每类检查：现状 + 你该看什么）

| 检查项 | 页面当前状态 | 若下列为真则勾选 |
|---|---|---|
| **Wrong period** | 目标期 FY2025；证据期间 Total assets: — → 2025-06-30 | 证据期间 ≠ 目标期间 |
| **Future source** | filing 日期 晚于期间结束 (2025-07-30)；cutoff 2025-07-30 00:00:00 | filing 晚于 cutoff 或无法确认期间归属 |
| **Version/amendment unclear** | form 10-K；amendment 未检出 | 存在 amendment/restatement 或版本关系不明 |
| **Metric definition unclear** | 定义 已显式声明 | 定义未定稿或概念映射(问题词汇→概念)不成立 |
| **Unit/scale unclear** | 单位 — | 单位不一致或与问题要求不符 |
| **Wrong entity** | issuer — | issuer ≠ 问题主体 |
| **Missing evidence** | 已解析证据 1 行；计算输入 0 个 | 计算所需输入缺行 |
| **No issue found** | — | 以上各项均无异常 |

**请回答 Q1-Q5 + 置信度。**