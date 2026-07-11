# Limitations

## Data Limitations

- **Small corpus:** Only 12 reports from 4 issuers
- **Small label set:** 32 labeled questions (16 qualitative + 16 audit)
- **No inter-annotator agreement:** Labels are single-annotator
- **Synthetic corpus:** Production corpus requires PDF Manager integration
- **No real PDFs committed:** Source documents fetched from official archives

## Model Limitations

- **Fixture mode:** Default testing uses deterministic fixtures, not production models
- **Model availability:** Production models require internet access for first download
- **No fine-tuning:** Models used as-is from HuggingFace
- **Small embedding dimension:** all-MiniLM-L6-v2 has 384 dimensions

## Calibration Limitations

- **Conservative policy:** Frozen threshold near 1.0 yields ~4% coverage
- **Small calibration set:** Only 56 samples across 4 folds
- **No cross-validation:** Leave-one-issuer-out is the only validation
- **Fixture calibrator:** Production requires fitted Platt scaling

## Retrieval Limitations

- **Deterministic fixtures:** Production backends may produce different results
- **No learning-to-rank:** Simple score-based ranking
- **Limited temporal reasoning:** Basic valid-time and source-time filtering
- **No contradiction detection:** Contradiction F1 is 1.0 in current results (no contradictions in fixture corpus)

## Attestation Limitations

- **Fixture signing:** No real secp256k1 signing implemented
- **No Solidity verification:** Cross-language verification requires GBL Task 12/14
- **Research prototype:** Not for production financial decisions

## Ethical Considerations

- **Not investment advice:** All outputs are sensitivity analysis only
- **No real predictions:** Results are model-driven parameters
- **No regulatory compliance:** Research prototype only
- **No production deployment:** For educational and portfolio use
