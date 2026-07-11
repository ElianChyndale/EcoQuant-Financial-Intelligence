# Failure Cases

## Known Failure Modes

### 1. Model Loading Failure

**Symptom:** RuntimeError: "Failed to load production dense model"
**Cause:** Sentence-transformers model not available or incompatible format
**Mitigation:** Use --fixture flag for offline environments
**Impact:** Research pipeline cannot run in production mode

### 2. Empty Corpus

**Symptom:** ValueError: "corpus must contain at least one record"
**Cause:** No documents loaded
**Impact:** All retrieval fails

### 3. Missing Graph

**Symptom:** ValueError: "KG retrievers require a TemporalEvidenceGraph"
**Cause:** KG methods used without graph
**Impact:** Static and temporal KG methods fail

### 4. Insufficient Evidence

**Symptom:** Decision = INSUFFICIENT_EVIDENCE
**Cause:** No results returned or extraction invalid
**Impact:** No valuation adjustment applied

### 5. Non-Finite Probability

**Symptom:** Decision = HUMAN_REVIEW_REQUIRED
**Cause:** NaN or infinity in calibrated probability
**Impact:** Cannot produce AUTO_REPORT

### 6. Gold Leakage

**Symptom:** Inflated performance metrics
**Cause:** Gold labels used in features (now fixed)
**Impact:** Results not representative of production

### 7. Silent Fallback (Fixed)

**Symptom:** Production metadata with fixture scores
**Cause:** Model load failure caught silently (now raises RuntimeError)
**Impact:** Misleading results

## Recovery Procedures

### Model Issues
```bash
# Clear cache and re-download
rm -rf ~/.cache/huggingface/hub/models--sentence-transformers--*
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### Fixture Mode
```bash
# Run with fixture backends
python scripts/run_research.py --seed 20260710 --fixture
```

### Test Failures
```bash
# Run specific test suite
python -m pytest tests/research/test_retrieval_methods.py -v
```
