# 05 — Research Gap and Novelty Matrix (FinVEST Redesign Phase 0)

**Date:** 2026-08-06
**Status:** PLANNING — defensible novelty positioning.

---

## 1. The proposed contribution

**FinVEST-Bench** + **VISTA-Fin** + **Human Decision Utility Study**.

Central task: retrieve a **minimum, sufficient, time-valid, version-consistent,
numerically-executable evidence set** for a financial question over a full
document universe; route ANSWER / REVIEW / ABSTAIN only when the set satisfies
all constraints.

## 2. Novelty matrix (vs related work)

| Work | What it does | What it does NOT do | FinVEST gap |
|---|---|---|---|
| **FinanceBench** | 150-sample financial QA, page-level evidence | single-page relevance; no set-level sufficiency; no paired counterfactuals | FinVEST adds set-level requirements, versions, paired conditions |
| **GRI-QA** | env-table QA, 8 op types | no full-document retrieval (tables given); no version/temporal | FinVEST adds full-corpus retrieval + version semantics |
| **FinQA / MultiHiertt** | financial program reasoning over tables | tables pre-selected; no document retrieval; no evidence-set minimality | FinVEST links executable programs to retrieved evidence sets |
| **FinMRAGBench** | 887 expert-verified cross-doc QA | no evidence-set sufficiency; no counterfactual conditions | FinVEST adds set-level + paired conditions |
| **FinRAGBench-V** | 110k+ pages, visual citation | no set-level sufficiency; no executable verification | FinVEST adds set-level + execution |
| **FinChain** | 58 topics, executable Python templates | symbolic pretraining; no real-document retrieval linkage | FinVEST connects executable verification to real retrieved evidence |
| **SURE-RAG** | set-level evidence sufficiency + selective answering | financial-specific: no units/periods/versions; no executable calc; no paired financial counterfactuals | **Closest** — FinVEST adds financial temporal/version/unit/executable dimensions |
| **HoH** | outdated-info effect on RAG | no evidence-set minimality; no amendment/version graphs | FinVEST adds version graphs + minimal sets |
| **DAPR** | document-aware passage retrieval | no evidence sufficiency; no selective control | FinVEST adds set-level sufficiency + routing |
| **TRAQ** | conformal prediction for RAG | no evidence-set semantics; exchangeability assumptions stated | FinVEST reuses conformal only under exchangeability (A6) |
| **AttributionBench** | automatic attribution evaluation difficulty | no set-level task; no financial versioning | FinVEST treats attribution as one layer, not the claim |
| **RAGTruth / GaRAGe** | hallucination detection / attribution | no minimum-sufficient-set task | FinVEST task is set construction, not hallucination labeling |
| **ColPali / ViDoRe** | visual document retrieval | no financial evidence-set semantics | FinVEST uses visual retrieval as a stage, not the contribution |

## 3. The defensible intersection

None of the above defines **the unified task**: full-corpus financial retrieval
→ requirement-level completeness → minimum sufficient evidence-set selection →
source/valid-time/version consistency → executable financial calculation →
leakage-free selective risk control → measured human-review utility.

SURE-RAG is the closest (set-level sufficiency + selective answering). FinVEST's
differentiators vs SURE-RAG:
1. **Financial requirement graph** (entity/metric/period/unit/scale/scope/version
   nodes) instead of generic relevance.
2. **Version/amendment relations** (10-K vs 10-K/A) as first-class constraints.
3. **Executable calculation** as a sufficiency condition (program must reproduce
   the answer from the set).
4. **Paired financial counterfactuals** (wrong period/scope/unit/version swaps).
5. **Full-document corpus** (no gold-page filtering).

## 4. Risk: is this a "benchmark resource" or a "method" paper?

- If VISTA-Fin's set selector clearly beats strong baselines on
  All-Required-Evidence Recall + False-Support Rate with cross-dataset
  transfer → **main conference**.
- If the method gains are modest but the benchmark is rigorous + negative
  results are valuable → **Findings / resource paper** (codex's explicit
  fallback; both are acceptable).
