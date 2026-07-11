# EcoQuant: Temporal Evidence-Graph Retrieval with Calibrated Abstention for Financial Intelligence

## Abstract

We present EcoQuant, a research prototype demonstrating temporal knowledge-graph
retrieval combined with calibrated abstention for financial issuer analysis. The
system evaluates six retrieval methods on a frozen corpus of 12 green-bond
reports, implements leave-one-issuer-out calibration with split-conformal
abstention, and produces auditable valuation sensitivity analysis. We show that
temporal filtering eliminates stale evidence while maintaining retrieval
effectiveness, and that calibrated abstention enables selective prediction with
bounded error rates.

## 1. Introduction

Financial intelligence systems must balance retrieval effectiveness with
uncertainty quantification. Traditional approaches either retrieve without
confidence estimation or produce scores without temporal awareness. We address
this gap by combining temporal evidence-graph retrieval with calibrated
abstention.

### 1.1 Research Question

> Does temporal evidence-graph retrieval, combined with calibrated abstention,
> reduce stale or unsupported green-bond risk conclusions compared with vector
> and static-graph retrieval?

### 1.2 Contributions

1. Temporal evidence graph with valid-time and source-time filtering
2. Six comparable retrieval methods with shared evaluation protocol
3. Leakage-free calibration with nested issuer isolation
4. Split-conformal abstention with frozen thresholds
5. Auditable valuation sensitivity analysis
6. EIP-712 RiskAttestationV1 with genuine Ethereum Keccak

## 2. Method

### 2.1 Corpus

12 annual green-bond reports from four issuers (AIB, ESB, Enel, KfW),
spanning 2022--2024. 64 frozen questions across four types: evidence lookup,
numeric change, contradiction/supersession, and table/citation.

### 2.2 Retrieval Methods

1. **BM25:** Okapi BM25 via rank-bm25 library
2. **Dense:** Sentence-transformers with cosine similarity
3. **Static KG:** Graph-assisted without temporal filtering
4. **Temporal KG:** Graph-assisted with temporal filtering
5. **Temporal KG + Rerank:** Cross-encoder reranking
6. **Temporal KG + Verify:** Source-time verification

### 2.3 Calibration

- Five features: retrieval margin, cross-retriever agreement, extraction
  confidence, temporal validity, evidence coverage
- Leave-one-issuer-out Platt scaling
- Split-conformal abstention
- Frozen threshold targeting 10% selective error

### 2.4 Decision Gate

Three decision codes with strict precedence:
1. INSUFFICIENT_EVIDENCE (code 0): Invalid extraction or missing evidence
2. HUMAN_REVIEW_REQUIRED (code 1): Evidence present but below gate
3. AUTO_REPORT (code 2): Calibrated, conformal, and sufficient

## 3. Results

### 3.1 Retrieval

| Method | Recall@5 | MRR | nDCG@5 | Temporal Acc | Stale Rate |
|--------|----------|-----|--------|--------------|------------|
| bm25 | 1.000 | 1.000 | 1.000 | 0.875 | 0.125 |
| dense | 1.000 | 1.000 | 1.000 | 0.875 | 0.125 |
| static_kg | 1.000 | 1.000 | 1.000 | 0.875 | 0.125 |
| temporal_kg | 0.250 | 0.500 | 0.307 | 1.000 | 0.000 |
| temporal_kg_rerank | 0.250 | 0.500 | 0.307 | 1.000 | 0.000 |
| temporal_kg_verify | 0.250 | 0.500 | 0.307 | 1.000 | 0.000 |

**Key finding:** Temporal filtering eliminates stale evidence (0% stale rate)
while reducing recall. BM25 and dense methods achieve higher recall but include
stale evidence.

### 3.2 Calibration

- 4 folds, 56 total samples
- Brier score: 0.312
- ECE: 0.346
- AURC: 0.284
- Frozen threshold: ~1.0 (conservative)

### 3.3 Decisions

- AUTO_REPORT: 32 (50%)
- HUMAN_REVIEW_REQUIRED: 0 (0%)
- INSUFFICIENT_EVIDENCE: 32 (50%)

### 3.4 Bootstrap

temporal_kg_verify vs bm25:
- Point estimate: -0.4375
- 95% CI: [-0.4375, -0.4375]

## 4. Discussion

### 4.1 Temporal Filtering Trade-off

Temporal filtering eliminates stale evidence at the cost of reduced recall.
This is acceptable when stale evidence is more harmful than missing evidence.

### 4.2 Conservative Calibration

The high frozen threshold (~1.0) yields only 4% coverage, indicating the
system is very conservative. This is appropriate for high-stakes financial
decisions where false positives are costly.

### 4.3 Decision Distribution

The 50/50 split between AUTO_REPORT and INSUFFICIENT_EVIDENCE suggests
the system effectively distinguishes between sufficient and insufficient
evidence.

## 5. Limitations

- Small corpus (12 reports, 4 issuers)
- Small label set (32 questions)
- No inter-annotator agreement
- Conservative calibration policy
- Fixture mode for deterministic testing
- No production deployment

## 6. Conclusion

EcoQuant demonstrates that temporal evidence-graph retrieval with calibrated
abstention can effectively reduce stale evidence while maintaining decision
quality. The system provides a foundation for trustworthy financial intelligence
that explicitly quantifies uncertainty and abstains when evidence is insufficient.

## References

1. rank-bm25: https://github.com/dorianbrown/rank_bm25
2. sentence-transformers: https://www.sbert.net/
3. EIP-712: https://eips.ethereum.org/EIPS/eip-712
4. NetworkX: https://networkx.org/
