# Case: finvest-AAPL-amended-AccruedLiabilitiesCurrent-2008-09-27

**问题**：What is the latest restated value of AccruedLiabilitiesCurrent for AAPL for the period ending 2008-09-27?

## 指标定义（显式）
本题为直接提取/事实性问题；请按页面证据表与时间版本卡判断。

## ① 原始 SEC 数据行（验证门禁——逐字来源，可独立核对）

```json
[
  {
    "concept": "AccruedLiabilitiesCurrent",
    "taxonomy": "us-gaap",
    "val": 3719000000.0,
    "unit": "USD",
    "start": "",
    "end": "2008-09-27",
    "fy": "2009",
    "fp": "FY",
    "form": "10-K",
    "filed": "2009-10-27",
    "accn": "0001193125-09-214859",
    "source_file": "research/cache/sec/aapl_companyfacts.json",
    "source_hash": "52343026847b8d2648e36237a90dc25186cf5e6f1f277f327e1ff5bdeffa87e4"
  },
  {
    "concept": "AccruedLiabilitiesCurrent",
    "taxonomy": "us-gaap",
    "val": 4224000000.0,
    "unit": "USD",
    "start": "",
    "end": "2008-09-27",
    "fy": "2009",
    "fp": "FY",
    "form": "10-K/A",
    "filed": "2010-01-25",
    "accn": "0001193125-10-012091",
    "source_file": "research/cache/sec/aapl_companyfacts.json",
    "source_hash": "c7cafae0113a904642dc2f02a3fd2742c9abc5c39600c4810c9c712c126350df"
  }
]
```
来源文件: research/cache/sec/aapl_companyfacts.json · sha256: 52343026847b8d26…

## ② 人类可读解读

- **Accrued liabilities, current**: 3,719,000,000 USD · FY2008 · 10-K · filed 2009-10-27 · accn 0001193125-09-214859
- **Accrued liabilities, current**: 4,224,000,000 USD · FY2008 · 10-K/A · filed 2010-01-25 · accn 0001193125-10-012091

## ④ 时间与版本卡
- 目标期: 2008 · source cutoff: 2010-01-25 00:00:00
- Accrued liabilities, current: — → 2008-09-27 · filed 2009-10-27 (10-K) · accn 0001193125-09-214859 · 晚于目标期=是
- Accrued liabilities, current: — → 2008-09-27 · filed 2010-01-25 (10-K/A) · accn 0001193125-10-012091 · 晚于目标期=是
*若 filing date 晚于目标期结束日，需自行判断：后发 10-K 是否包含目标期 comparative figures，是否存在 amendment/restatement，以及是否应优先使用 更接近目标期的原始 filing。*

## ⑤ Q4 判断对照表（每类检查：现状 + 你该看什么）

| 检查项 | 页面当前状态 | 若下列为真则勾选 |
|---|---|---|
| **Wrong period** | 目标期 2008；证据期间 Accrued liabilities, current: — → 2008-09-27；Accrued liabilities, current: — → 2008-09-27 | 证据期间 ≠ 目标期间 |
| **Future source** | filing 日期 晚于期间结束 (2009-10-27, 2010-01-25)；cutoff 2010-01-25 00:00:00 | filing 晚于 cutoff 或无法确认期间归属 |
| **Version/amendment unclear** | form 10-K, 10-K/A；amendment 存在: 10-K/A | 存在 amendment/restatement 或版本关系不明 |
| **Metric definition unclear** | 定义 已显式声明 | 定义未定稿或概念映射(问题词汇→概念)不成立 |
| **Unit/scale unclear** | 单位 — | 单位不一致或与问题要求不符 |
| **Wrong entity** | issuer — | issuer ≠ 问题主体 |
| **Missing evidence** | 已解析证据 2 行；计算输入 0 个 | 计算所需输入缺行 |
| **No issue found** | — | 以上各项均无异常 |

**请回答 Q1-Q5 + 置信度。**