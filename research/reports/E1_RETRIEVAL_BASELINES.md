# E1 — Real-Data Retrieval Baselines: FinanceBench Sample and EcoQuant Corpus

**Experiment:** e1-retrieval-baselines
**Date:** 2026-08-06
**Status:** INTERNAL PILOT — results valid on the two described datasets; not a
cross-dataset generalisation claim.
**Reproduction:** `python scripts/run_e1_retrieval.py` (writes
`research/results/e1_retrieval_summary.json`).
**Commit:** merged to `main` at `b8a761a`.

---

## 1. Research Question

> Does hybrid retrieval (BM25 + dense reciprocal-rank fusion) reliably beat the
> strongest single retriever on real financial documents?

**Falsifiable hypotheses:**

- H1: On both datasets, hybrid (B5) achieves higher Recall@5 than every single
  retriever (B1–B4).
- H2: Dense retrieval (B4) outperforms sparse (B1–B3) on real 10-K page retrieval
  (FinanceBench), because financial questions are semantically phrased rather than
  lexically matched.
- H3: The same method ranking holds across datasets (stable preference).

## 2. Datasets

### 2.1 FinanceBench public sample

- 150 questions over real 10-K/10-Q/8-K/earnings reports of **32 public companies**
  (84 documents, 168 unique evidence pages).
- Gold = human-annotated answer + evidence pages (`evidence_page_num`, zero-indexed).
- Corpus = the 168 unique evidence pages, text = `evidence_text_full_page`.
- License unconfirmed → `cache_only`, raw JSONL not committed (hashes only).
- Page convention: zero-indexed int (differs from EcoQuant's `p63`).

### 2.2 EcoQuant corpus

- 64 questions over 12 public green-bond reports (4 issuers × 3 years).
- Corpus = 24 unique `(source, page, block)` evidence records after dedup.
- **Known limitation:** corpus text is generic ("evidence for issuer … source …
  page … block"), not the real document content. Results on this corpus are
  **near-saturated** and should not be over-interpreted.

## 3. Method

Six baselines over a shared corpus, top-k=5, deterministic tie-break by
evidence_id:

| ID | Method | Implementation |
|---|---|---|
| B1 | BM25 | `rank_bm25` BM25Okapi |
| B2 | TF-IDF | scikit-learn `TfidfVectorizer` + cosine |
| B3 | LSA | TF-IDF + TruncatedSVD(≤128) + cosine |
| B4 | Dense | `all-MiniLM-L6-v2` (locally cached) + cosine |
| B5 | Hybrid RRF | BM25 + dense ranks fused with RRF (k=60) |
| B7 | Long-context | full-document query-term overlap |

**Evaluation:** `score_retrieval` (Recall@5, Hit@5, MRR, nDCG@5, page accuracy);
95% company-clustered bootstrap CIs (FinanceBench) / issuer-clustered (EcoQuant)
via `paired_issuer_clustered_bootstrap` (1,000 samples, seed `20260710`).

**Blocked baseline:** B6 (cross-encoder reranker `BAAI/bge-reranker-base`) remains
blocked by an external model asset. It is explicitly **not** faked or substituted.

## 4. Results

### 4.1 FinanceBench (150 questions, 168 pages)

| Method | Recall@5 | 95% CI | Hit@5 | MRR | nDCG@5 | PageAcc |
|---|---|---|---|---|---|---|
| **B4 dense** | **0.563** | [0.482, 0.650] | 0.660 | 0.387 | 0.422 | 0.633 |
| B5 hybrid_rrf | 0.511 | [0.434, 0.592] | 0.613 | 0.345 | 0.375 | 0.593 |
| B2 tfidf | 0.381 | [0.285, 0.477] | 0.400 | 0.263 | 0.286 | 0.447 |
| B3 lsa | 0.369 | [0.279, 0.461] | 0.393 | 0.253 | 0.274 | 0.440 |
| B1 bm25 | 0.287 | [0.205, 0.369] | 0.333 | 0.208 | 0.225 | 0.340 |
| B7 long_context | 0.277 | [0.190, 0.371] | 0.293 | 0.166 | 0.192 | 0.347 |

### 4.2 EcoQuant corpus (64 questions, 24 records)

| Method | Recall@5 | 95% CI | Hit@5 | MRR | nDCG@5 | PageAcc |
|---|---|---|---|---|---|---|
| B2 tfidf | 0.914 | [0.859, 0.969] | 0.969 | 0.977 | 0.876 | 1.000 |
| B3 lsa | 0.914 | [0.859, 0.969] | 0.969 | 0.977 | 0.876 | 1.000 |
| B1 bm25 | 0.891 | [0.781, 0.992] | 0.969 | 0.967 | 0.869 | 1.000 |
| B5 hybrid_rrf | 0.785 | [0.672, 0.898] | 0.922 | 0.896 | 0.753 | 1.000 |
| B4 dense | 0.734 | [0.672, 0.797] | 0.859 | 0.706 | 0.623 | 1.000 |
| B7 long_context | 0.727 | [0.562, 0.906] | 0.922 | 0.966 | 0.749 | 1.000 |

## 5. Findings

1. **H1 rejected (hybrid is not always best).** On FinanceBench, dense beats
   hybrid (0.563 vs 0.511, CIs [0.482,0.650] vs [0.434,0.592] — overlapping, so
   not a decisive separation, but dense is the point-estimate winner). On
   EcoQuant, hybrid is not the winner either (sparse TF-IDF/LSA lead).
2. **H2 supported on FinanceBench.** Dense clearly beats sparse on real 10-K page
   retrieval (0.563 vs 0.287–0.381, CI separation for BM25). Semantic phrasing of
   finance questions aligns with dense embeddings.
3. **H3 rejected (no stable ranking across datasets).** The method preference
   **reverses**: sparse wins on EcoQuant, dense wins on FinanceBench. The
   differences are plausibly driven by corpus text quality (EcoQuant generic
   text vs FinanceBench real page text) rather than by dataset size alone.

**Interpretation:** the E1 question "does hybrid reliably beat single retrieval"
has a **negative answer** on these two datasets. Method advantage is
**dataset-dependent**, and hybrid RRF sits between sparse and dense rather than
above both. This is a useful, honest finding: it argues against a one-size-fits-all
retrieval claim and motivates **dataset-adaptive method selection** (E1's proposed
"learned or rule-based query routing" direction) as future work.

## 6. Limitations

1. **EcoQuant corpus text is generic** (not real document content) → its results
   are near-saturated (PageAcc 1.0) and should not be over-interpreted.
2. **FinanceBench corpus is the evidence pages themselves** (gold and corpus are
   same-sourced) — a mild "near-loop" that can inflate absolute metrics. Relative
   method comparisons remain meaningful.
3. **B6 reranker not run** (external asset blocked). Hybrid here means RRF of
   BM25+dense, not reranking.
4. **CI overlap** between dense and hybrid on FinanceBench means the winner is not
   statistically decisive at 95%; the finding is "dense ≥ hybrid ≥ sparse" with
   clear sparse separation, not a claim that dense beats hybrid.
5. **No threshold/parameter tuning** was performed (frozen k=60 RRF, fixed SVD
   dims) — results are honest defaults, not tuned optima.

## 7. Claims Permitted After This Experiment

- **SUPPORTED:** On FinanceBench sample, dense retrieval achieves higher Recall@5
  than BM25/TF-IDF/LSA/long-context on 150 real 10-K questions.
- **SUPPORTED:** Hybrid RRF does not reliably beat the strongest single retriever
  on these two datasets.
- **PARTIALLY SUPPORTED:** Dense beats hybrid on FinanceBench by point estimate
  (CI overlap → not decisive).
- **PROHIBITED:** "state-of-the-art", "production-ready", "generalises to
  finance", "hybrid retrieval is best".

## 8. Reproduction

```bash
cd EcoQuant-Financial-Intelligence
python scripts/run_e1_retrieval.py   # needs research/cache/financebench/*.jsonl + models/
```

- Model: `all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (cached).
- FinanceBench raw JSONL is cache-only (hashes in bundle manifest).
- Seeds: RRF k=60 (fixed), SVD random_state=20260806, bootstrap seed=20260710.
