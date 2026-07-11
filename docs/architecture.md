# Architecture

## System Overview

EcoQuant Financial Intelligence is a research prototype for evidence-grounded,
uncertainty-aware financial analysis. It demonstrates temporal knowledge-graph
retrieval, calibrated abstention, and auditable valuation sensitivity.

## Data Flow

```
Official green-bond reports (PDF)
        |
        v
PDF Manager normalized_document_v1
        |
        v
EvidenceSpanV1 records
        |
        v
Temporal evidence graph (NetworkX)
        |
        v
Six retrieval methods (BM25, dense, static KG, temporal KG, rerank, verify)
        |
        v
Calibration features (retriever-visible only)
        |
        v
Leave-one-issuer-out Platt calibration
        |
        v
Split-conformal abstention
        |
        v
Decision gate (AUTO_REPORT / HUMAN_REVIEW / INSUFFICIENT_EVIDENCE)
        |
        v
Valuation sensitivity analysis
        |
        v
EIP-712 RiskAttestationV1 fixture
```

## Trust Boundary

EcoQuant produces recommendations but never executes financial actions:

- **EcoQuant owns:** Document extraction, retrieval, calibration, valuation sensitivity
- **GBL owns:** Identity, bonds, settlement, lending, liquidation
- **Interface:** Signed EIP-712 RiskAttestationV1

AI cannot directly move funds or trigger liquidation.

## Components

### Document Intelligence
- `EvidenceSpanV1` schema for normalized document ingestion
- SHA-256 content hashing for provenance
- Integration with PDF Manager

### Evidence Graph
- Typed nodes: Issuer, Bond, Document, Claim, Event, Metric, RiskDriver
- Relations: ISSUED, CONTAINS, SUPPORTS, CONTRADICTS, SUPERSEDES, AFFECTS, VALID_AT, SOURCED_AT
- Evaluator-only edges blocked from retrieval

### Retrieval
- **BM25:** Okapi BM25 via rank-bm25 library
- **Dense:** Sentence-transformers with cosine similarity
- **Static KG:** Graph-assisted without temporal filtering
- **Temporal KG:** Graph-assisted with valid-time and source-time filtering
- **Temporal KG + Rerank:** Cross-encoder reranking
- **Temporal KG + Verify:** Source-time verification

### Uncertainty
- Five calibration features (no gold leakage)
- Platt scaling with gradient descent
- Leave-one-issuer-out folds
- Split-conformal abstention
- Three decision codes with strict precedence

### Valuation
- Bond cash-flow pricing with duration and convexity
- Evidence-to-risk-factor-to-channel mapping
- Bounded spread and haircut adjustments
- Sensitivity analysis (not investment advice)

### Attestation
- EIP-712 RiskAttestationV1
- Genuine Ethereum Keccak-256
- Merkle evidence root
- Domain separation by chain ID and adapter address
