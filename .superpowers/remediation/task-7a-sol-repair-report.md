# Task 7A Sol Valuation Repair Report

**Date:** 2026-07-13  
**Status:** SOL-2 fixed; fresh independent financial review required

## Frozen convention

The authoritative contract is recorded in
`docs/remediation/SOL2_VALUATION_CONVENTION.md`. Task 7A now uses explicit
issue, settlement, and maturity dates; unadjusted calendar coupon dates
generated backward from maturity; Actual/Actual ICMA quasi-coupon fractions;
and nominal annual yield compounded at coupon frequency. The production path
does not accept `maturity_years`, use `days/365.25`, or infer an irregular
schedule.

Regular schedules require issue to lie on the coupon grid. Initial and final
stubs are explicit through `first_coupon_date` and
`penultimate_coupon_date`, respectively. Stub coupon amounts, accrued interest,
discount timing, duration, and convexity use the same ICMA quasi-period
partition. More-than-two-period or internally unaligned stubs fail.

Cash flows on or before settlement are excluded. Dirty price is the present
value of remaining cash flows; clean price is dirty price less accrued interest.
Principal is attached to the maturity cash flow exactly once. No business-day,
ex-coupon, floating-rate, amortizing, or defaulted-cash-flow behavior is claimed.

## Confirmed defects and RED evidence

- The explicit `maturity_date` test failed because the old API accepted only
  `maturity_years`; the legacy fractional-years rejection test also failed
  because `5.5` was silently accepted and truncated.
- The 20-test pricing fixture file failed completely on the old boundary.
- Five provenance tests failed because `asset_id` and the complete convention/
  repricing state were absent and a risk-factor fallback could replace a real
  evidence ID.
- Four missing-evidence/non-finite-policy tests failed because an empty evidence
  set could adjust an `AUTO_REPORT` policy and non-finite risks were clamped.
- Five invalid-bps/out-of-range-risk tests failed because policy inputs were not
  validated.
- A three-period first-stub test failed because the prototype initially allowed
  an unsupported stub longer than the frozen two-period limit.
- The policy-to-provenance integration test failed because an unsupported
  factor was not carried into a visible no-adjustment record.

## Independent fixtures and risk verification

Hand-computed regular fixtures cover zero-coupon, par, premium, and discount
bonds. A between-coupon fixture independently calculates the 89/181 accrued
fraction, 92/181 first discount exponent, dirty price, and clean/dirty identity.
Irregular fixtures calculate short and long first and final stub coupons from
actual quasi-period day counts. Additional fixtures cover settlement on a
coupon date, leap-year/month-end dates, principal uniqueness, and a +100-bps
spread shock.

Analytical Macaulay duration, modified duration, and convexity use the same ICMA
cash-flow timing as price. Central finite differences use a one-basis-point
nominal annual yield perturbation for a regular coupon-date case, a
between-coupon case, and a short-stub case. A separate test confirms the
second-order convexity approximation improves on modified duration alone.
Fixture tolerances are `1e-12` relative for direct formulas and `2e-7`/
`2e-6` relative for numerical duration/convexity, allowing floating-point
roundoff without masking convention errors.

## Evidence-to-valuation provenance

Every supported scenario retains the actual evidence ID, issuer, asset ID,
risk factor/channel, rule ID/version, base/adjusted spread, distinct valid and
source times, decision code, day-count and compounding conventions, settlement
and maturity dates, frequency, base/adjusted clean and dirty prices, accrued
interest, Macaulay duration, modified duration, and convexity. Empty evidence
IDs fail instead of falling back to a factor name.

Risk-channel mapping now occurs before policy spread and haircut calculations.
Unsupported factors cannot alter either output and are carried into explicit
`unsupported_risk_mapping` rows with zero spread and haircut deltas. Every
supported spread scenario is repriced from cash flows.

## Focused verification

```text
python -m pytest -q -p no:cacheprovider tests/unit/test_bond_pricing.py tests/unit/test_valuation_provenance.py tests/unit/test_valuation_policy.py tests/unit/test_attestation.py::TestBondPricing tests/unit/test_attestation.py::TestInputValidation tests/unit/test_attestation.py::TestZeroCouponBond tests/unit/test_attestation.py::TestBetweenCouponSettlement tests/unit/test_attestation.py::TestExplicitMaturity tests/unit/test_attestation.py::TestLeapYearHandling tests/unit/test_attestation.py::TestUnsupportedMapping tests/unit/test_attestation.py::TestEvidenceProvenance
90 passed
```

The broader Task 7A-adjacent focused command including the existing attestation
file reports 121 passed. No full EcoQuant suite was run in this session.

## Claim boundary and limitations

The module supports claims of transparent model sensitivity, reproducible
cash-flow repricing, and bounded evidence-to-spread scenarios. It does not
claim observed-market calibration, external rating accuracy, investment
performance, regulatory approval, production pricing, or investment advice.
No Task 7A GO is declared by this report.
