# Task 6 Statistical Repair Report

**Date:** 2026-07-13
**Status:** SOL-1 conceptual corrections complete; independent review required

## Frozen target and leakage boundary

The calibrated probability estimates the binary benchmark target
`correct_and_supported`. It is true exactly when the primary retriever's
top-ranked evidence identifier is in the evaluator's relevant-evidence set and
that same retrieved record is both temporally valid and source verified. The
same Boolean target is used for Platt fitting, conformal calibration,
decision-threshold selection, outer evaluation, and reported metrics.

Gold evidence identifiers are used only to construct this fit/calibration/
evaluation label. Gold answers, expected numeric values, citations,
contradictions, pages, blocks, and outer outcomes are not production features
or decision inputs. Adversarial tests make forbidden evaluator fields raise on
access during feature construction.

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
- Decision thresholds are learned on the separate threshold-selection issuer.
  Each manifest freezes the learned probability and conformal thresholds, the
  `0.25` evidence-sufficiency threshold, and mandatory extraction-validity and
  temporal-validity gates. Final execution rejects missing policy state and
  consumes that manifest rather than reconstructing a default.

Cross-retriever agreement always uses the six registered method slots. Missing
method keys fail. Evidence coverage is the proportion of five frozen result
slots occupied by temporally valid, source-verified evidence from the primary
graph-verification retriever; it is independent of score scale and gold IDs.

Reported Brier score, equal-width-bin ECE, risk-coverage points, and AURC are
computed from pooled outer predictions and labels. Risk-coverage output contains
one measured row per outer record, not placeholder fold rows. Coverage and
selective risk at the operating point use each record's fold-specific frozen
threshold. An abstain-all selective risk is serialized as `null` with
`evaluable=false` and reason `no_accepted_records`. The AURC convention includes
the rectangle from coverage zero to the first accepted point, then trapezoidal
integration between subsequent points; the one-record case follows the same
convention.

## RED/GREEN evidence

SOL-1 RED failures reproduced:

```text
2 failed: gold-matching stale or unverified evidence was labelled supported
1 failed: selective threshold metric helper was absent
1 failed: measured risk_coverage output was absent
5 failed: singleton AURC and malformed metric inputs violated the convention
1 failed: complete frozen decision policy was absent from fold manifests
```

The hostile contract separately mutates outer labels and outer predictions and
requires byte-identical frozen fit/calibration state. It also verifies fit-label
sensitivity, disjoint issuer roles, held-out exclusion, non-convergence blocking,
degenerate-label rejection, and forbidden evaluator-field isolation.

Focused GREEN:

```text
python -m pytest -q -p no:cacheprovider tests/research/test_calibration_protocol.py tests/unit/test_decision_gate.py tests/research/test_task6_statistical_contract.py
95 passed
```

No full EcoQuant suite was run in this SOL-1 session; that gate remains reserved
for SOL-4.

## Limitations and prohibited claims

- The frozen study has only four issuers, leaving one issuer per inner role.
- Exchangeability is an explicit modelling assumption and is not established
  by this small heterogeneous sample.
- No finite-sample guarantee is claimed beyond the stated split-conformal
  assumptions.
- Calibration performance remains unverified on production retrieval outputs.
- The current retrieval boundary does not expose the source span's extraction
  confidence. Task 6 therefore uses a bounded normalized retrieval-score proxy
  in the consistently shared feature builder. Replacing that proxy requires a
  separately approved upstream retrieval/schema contract and was not redesigned
  in SOL-1.
- This report does not declare Task 6 GO.
