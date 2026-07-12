# Task 6 Statistical Repair Report

**Date:** 2026-07-12
**Status:** Implementation complete; independent statistical review required

## Frozen target and leakage boundary

The calibrated probability estimates the binary benchmark target
`correct_and_supported`: the retrieval/answer output satisfies the frozen
correctness and evidence-support criteria. Gold correctness is used only as a
fit/calibration/evaluation target. Gold evidence IDs, answers, pages, blocks,
and outer outcomes are not production features or decision inputs.

Each outer issuer fold reserves four disjoint roles:

1. held-out outer evaluation issuer;
2. fit issuer(s) for normalization and Platt coefficients;
3. conformal-calibration issuer;
4. decision-threshold-selection issuer.

With the frozen four-issuer study, each role contains exactly one issuer.
Fewer than four issuers is rejected rather than silently reusing an issuer.

## Statistical contract

- Platt fitting uses deterministic L2-regularized Newton/IRLS optimization.
- Fitted state records objective, iteration count, convergence, degeneracy,
  and failure reason.
- Empty, non-finite, misaligned, or one-class fit data is rejected.
- Final decisions reject unconverged or non-finite fitted state.
- Correctness nonconformity is `1 - p` for observed correct examples and
  `p` for observed incorrect examples.
- At decision time the candidate `correct_and_supported=True` score is
  `1 - p`.
- The finite-sample quantile is
  `ceil((n + 1) * (1 - alpha))`, clipped to `[1, n]`.
- Larger scores are worse; equality at the threshold is accepted.
- Decision thresholds are learned on the separate threshold-selection issuer
  and consumed through an immutable fold-specific `DecisionPolicy`.

Cross-retriever agreement always uses the six registered method slots. Missing
method keys fail. Evidence coverage is the proportion of five frozen result
slots occupied by temporally valid, source-verified evidence from the primary
graph-verification retriever; it is independent of score scale and gold IDs.

## RED/GREEN evidence

Initial RED:

```text
ImportError: cannot import name 'require_final_calibration'
```

The new contract also reproduced the previous acceptance of degenerate labels,
issuer-role reuse, hardcoded decision threshold, score-scale-sensitive coverage,
and missing convergence enforcement.

Focused GREEN:

```text
python -m pytest -q -p no:cacheprovider +  tests/research/test_calibration_protocol.py +  tests/unit/test_decision_gate.py +  tests/research/test_task6_statistical_contract.py
80 passed
```

Full regression:

```text
python -m pytest -q -p no:cacheprovider
248 passed
```

An isolated fixture execution completed with four converged calibrators in
five to six iterations. This is fixture evidence, not a production performance
claim.

## Limitations and prohibited claims

- The frozen study has only four issuers, leaving one issuer per inner role.
- Exchangeability is an explicit modelling assumption and is not established
  by this small heterogeneous sample.
- No finite-sample guarantee is claimed beyond the stated split-conformal
  assumptions.
- Calibration performance remains unverified on production retrieval outputs.
- This report does not declare Task 6 GO.
