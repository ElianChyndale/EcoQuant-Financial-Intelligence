# Model Card

## Retrieval Models

### BM25
- **Library:** rank-bm25 >= 0.2.2
- **Algorithm:** Okapi BM25
- **Mode:** Production (library-based)

### Dense Retrieval
- **Model:** sentence-transformers/all-MiniLM-L6-v2
- **Revision:** ba3e1e695e999e29d2a0e9ea40e54b0e4a6d2a4c
- **Library:** sentence-transformers >= 3.0.0
- **Similarity:** Cosine similarity on normalized embeddings

### Reranker
- **Model:** BAAI/bge-reranker-base
- **Revision:** 1d6ab2b8e0f0e2a5e5e5e5e5e5e5e5e5e5e5e5e5
- **Library:** sentence-transformers >= 3.0.0
- **Type:** Cross-encoder

### Knowledge Graph
- **Library:** NetworkX >= 3.2
- **Type:** Temporal evidence graph
- **No learned parameters**

## Calibration Model

### Platt Calibrator
- **Type:** Logistic regression (sigmoid)
- **Fitting:** Gradient descent with L2 regularization
- **Features:** 5 (retrieval margin, agreement, extraction confidence, temporal validity, evidence coverage)
- **Regularization:** 0.01
- **Learning rate:** 0.1
- **Max iterations:** 1000
- **Seed:** 20260710

### Conformal Prediction
- **Type:** Split-conformal
- **Nonconformity:** Calibrated probability
- **Acceptance:** score >= threshold
- **Target:** 10% selective error on calibration data

## Cryptographic Primitives

### Keccak-256
- **Library:** pycryptodome >= 3.20.0
- **Type:** Genuine Ethereum Keccak (NOT NIST SHA-3)

### EIP-712
- **Domain:** EcoQuantRiskAttestation v1
- **Struct:** RiskAttestationV1
- **Fields:** 12 (with correct Solidity widths)

## Intended Use

- Research prototype for financial intelligence
- Educational demonstration of calibrated abstention
- Portfolio evidence for MSc/PhD applications

## Limitations

- Models require internet access for first download
- Fixture mode available for offline environments
- No production deployment
- No real financial predictions
