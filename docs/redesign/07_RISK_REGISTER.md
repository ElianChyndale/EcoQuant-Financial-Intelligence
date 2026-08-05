# 07 — Risk Register (FinVEST Redesign)

**Date:** 2026-08-06
**Status:** LIVING — updated as the redesign proceeds.

---

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **Benchmark contamination** — public data in model training | HIGH | dynamic sealed test (post-cutoff filings); contamination policy; never claim SOTA |
| 2 | **Annotation cost/quality** — 2,000 cases × paired conditions | HIGH | annotation tooling; AI pre-annotations hidden from second annotator; adjudication; α ≥ 0.75 gate |
| 3 | **VISTA-Fin fails to beat baselines** | MEDIUM | preregistered negative result → Findings/resource paper (explicit fallback) |
| 4 | **Gold leakage (as in E5)** | HIGH | leak-free guard test (done); 5-level splitter; leakage auditor CI |
| 5 | **Full-document retrieval is much harder** (oracle gap large) | MEDIUM | honest A1 report; method positioned on the full-corpus task |
| 6 | **ESEF access/licensing** | MEDIUM | verify per-issuer; if blocked, US-only track (documented) |
| 7 | **Human study infeasible** (recruiting 24-30) | MEDIUM | E6 remains researcher-driven; protocol + interface ready; report when data collected |
| 8 | **GPU/model assets missing** (BGE-M3, ColPali, reranker) | MEDIUM | text-first pipeline; visual/reranker as optional stages; document what's blocked |
| 9 | **Scope creep** (feature expansion again) | HIGH | single task definition; milestone gates; reject new experiments not serving the thesis |
| 10 | **Statistical misuse** (retriever outputs as independent samples) | MEDIUM | question/issuer/document-family as unit; clustered bootstrap; Holm correction |
| 11 | **Unsupported claims leak into public surfaces** | HIGH | claim-evidence matrix; A0 gates; invalidated-claims doc enforced |
| 12 | **Private/commercial data mixed with public benchmark** | HIGH | strict separation; private pilots never mixed (existing rule) |

## Watch items

- SURE-RAG is the closest related work — track its follow-ups.
- ACL/EMNLP deadlines: preregistration BEFORE headline eval is non-negotiable.
- If the method gains are modest, the benchmark + negative results are the
  paper — do not tune on test to force significance.
