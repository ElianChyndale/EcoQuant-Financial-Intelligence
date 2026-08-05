# 03 — Supported Pilot Claims (FinVEST Redesign Phase 0)

**Date:** 2026-08-06
**Status:** SUPPORTED as component claims (not headline research results).

These claims survive audit as *component-level* findings. They are inputs to
the redesign, not its outputs.

---

## Supported (with exact scope)

| Claim | Scope | Evidence |
|---|---|---|
| Dataset adapters separate gold from public query cases (E0) | EcoQuant corpus + FinanceBench | `datasets/`, integrity tests |
| Gold-mutation does not change retrieval ranking (E0) | corpus-level | `test_e0_integrity.py` |
| Scale-normalized matching is necessary for number grounding (E4) | FinanceBench answers | `verifier.py`, E4 report |
| The multi-layer verifier rejects injected ungrounded numbers (E4) | 30-case stress test | `e4_verification_summary.json` |
| SEC XBRL adapter handles heterogeneous fiscal years (E7) | AAPL/MSFT/JNJ/UPS/KO/EQIX | `concepts.py`, tests |
| Commercial ratios computed from raw XBRL match public financials (E7) | 6 companies spot-checked | `e7_commercial_summary.json` |
| The AI/non-AI boundary is enforceable (E8) | 6-case demo | `e8_integration_summary.json` |
| Decision gate + RiskAttestationV1 routing works (E8) | architecture | `integration_eval/`, SOL-3 tests |

## Not yet supported (need redesign experiments)

| Claim | Why not supported |
|---|---|
| Dense beats sparse on real full documents | E1 used gold-page corpus |
| Separated calc is end-to-end reliable | E2 used gold cells |
| Temporal filters work jointly | E3 optimized separately |
| Calibration enables selective prediction | E5 had gold-derived feature (now fixed; leak-free rerun AUROC 0.719 is the honest baseline) |
| Evidence packages help human reviewers | No human study (E6) exists |
