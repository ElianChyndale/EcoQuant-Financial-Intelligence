# Case: finvest-KO-extractive-Revenues-2023

**问题**：What is Revenues for KO for fiscal year 2023?

## 指标定义（显式）
本题为直接提取/事实性问题；请按页面证据表与时间版本卡判断。

## ① 原始 SEC 数据行（验证门禁——逐字来源，可独立核对）

```json
[
  {
    "concept": "Revenues",
    "taxonomy": "us-gaap",
    "val": 45754000000.0,
    "unit": "USD",
    "start": "2023-01-01",
    "end": "2023-12-31",
    "fy": "2023",
    "fp": "FY",
    "form": "10-K",
    "filed": "2024-02-20",
    "accn": "0000021344-24-000009",
    "source_file": "research/cache/sec/ko_companyfacts.json",
    "source_hash": "ac57615c61f6437df6196e4051c35c711fa140a313bec7daac96129e84ee5a43"
  }
]
```
来源文件: research/cache/sec/ko_companyfacts.json · sha256: ac57615c61f6437d…

## ② 人类可读解读

- **Revenues**: 45,754,000,000 USD · FY2023 · 10-K · filed 2024-02-20 · accn 0000021344-24-000009

## ④ 时间与版本卡
- 目标期: FY2023 · source cutoff: 2024-02-20 00:00:00
- Revenues: 2023-01-01 → 2023-12-31 · filed 2024-02-20 (10-K) · accn 0000021344-24-000009 · 晚于目标期=是
*若 filing date 晚于目标期结束日，需自行判断：后发 10-K 是否包含目标期 comparative figures，是否存在 amendment/restatement，以及是否应优先使用 更接近目标期的原始 filing。*

## ⑤ Q4 判断对照表（每类检查：现状 + 你该看什么）

| 检查项 | 页面当前状态 | 若下列为真则勾选 |
|---|---|---|
| **Wrong period** | 目标期 FY2023；证据期间 Revenues: 2023-01-01 → 2023-12-31 | 证据期间 ≠ 目标期间 |
| **Future source** | filing 日期 晚于期间结束 (2024-02-20)；cutoff 2024-02-20 00:00:00 | filing 晚于 cutoff 或无法确认期间归属 |
| **Version/amendment unclear** | form 10-K；amendment 未检出 | 存在 amendment/restatement 或版本关系不明 |
| **Metric definition unclear** | 定义 已显式声明 | 定义未定稿或概念映射(问题词汇→概念)不成立 |
| **Unit/scale unclear** | 单位 — | 单位不一致或与问题要求不符 |
| **Wrong entity** | issuer — | issuer ≠ 问题主体 |
| **Missing evidence** | 已解析证据 1 行；计算输入 0 个 | 计算所需输入缺行 |
| **No issue found** | — | 以上各项均无异常 |

**请回答 Q1-Q5 + 置信度。**