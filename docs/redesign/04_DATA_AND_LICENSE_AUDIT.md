# 04 — Data and License Audit (FinVEST Redesign Phase 0)

**Date:** 2026-08-06
**Status:** READ-ONLY INVENTORY — raw data is cache-only (gitignored).

---

## 1. Current cache inventory

| Dataset | Path (cache) | Content | License | Redistribution |
|---|---|---|---|---|
| EcoQuant corpus | `research/cache/` (OS temp for PDFs) | 64 q / 12 reports | public docs | cache-only |
| FinanceBench | `research/cache/financebench/` | 150 q / 168 pages / 84 docs | **unconfirmed** | cache-only |
| GRI-QA | `research/cache/griqa/` | 266 q / 27 tables | MIT | cache-only |
| SEC companyfacts | `research/cache/sec/` | 6 companies / 73k+ facts | public domain | cache-only |
| dense model | `research/cache/models/all-MiniLM-L6-v2` | 90MB weights | Apache-2.0 (HF) | local |

All raw data is gitignored (`research/cache/`); only hashes + derived metadata
committed. This is correct.

## 2. Redesign data needs (FinVEST-Bench)

| Need | Source | License action |
|---|---|---|
| Full 10-K documents (not gold pages) | SEC EDGAR filing API | public domain; must re-fetch full filings |
| 100 US issuers × 3-5 FY | SEC EDGAR | public domain |
| EU ESEF XHTML/iXBRL | ESMA / issuer sites | verify per-issuer license |
| 10-K/A, 10-Q/A amendments | SEC EDGAR submissions API | public domain |
| XBRL Company Facts (structured) | data.sec.gov | public domain |
| GRI-QA (sustainability) | softlab-unimore/gri_qa | MIT — **can redistribute with attribution** |
| FinanceBench full PDFs | patronus-ai/financebench | **unconfirmed — do not redistribute; fetch only** |
| FinMRAGBench / FinRAGBench-V / FinChain | ACL papers' repos | verify at fetch time |

## 3. Rules

1. No restricted raw data committed. Cache-only + hashes (current policy, keep).
2. GRI-QA MIT allows redistribution — may commit derived annotations with
   attribution.
3. FinanceBench license unconfirmed — fetch cache-only; cite upstream.
4. SEC public domain — safe to use for derived benchmark cases.
5. EU ESEF — per-issuer license check before any redistribution.
6. Every dataset card records: source, version/commit, license, retrieval
   date, hash, adapter version, exclusion log.
