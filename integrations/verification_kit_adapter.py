"""Adapter: dual-implementation verification + mutation challenges via
financial-systems-verification-kit (Phase 5.2).

Two capabilities wired into FinVEST:
  1. dual_check_ocf_capex — EcoQuant computes OCF - |CapEx|, the kit recomputes
     it with an independent Decimal implementation, pass iff both agree.
  2. generate_mutation_challenges — produce wrong-sign / scale-x1000 /
     USD-vs-millions / wrong-fiscal-year / swapped-order / stale-filing /
     future-source / amendment-mismatch variants of a correct case so the
     verifier can be tested on REJECTING errors, not just passing correct ones.

All kit imports are lazy so CI without the tool repo still passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DualCheck:
    """Result of the dual-implementation numerical check."""

    passed: bool
    ecoquant_result: float | None
    kit_result: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "ecoquant_result": self.ecoquant_result,
            "kit_result": self.kit_result,
            "reason": self.reason,
        }


def _dec_str(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    f = float(value)
    return f"{f:.0f}" if f.is_integer() else str(f)


def dual_check_ocf_capex(
    operating_cash_flow: Any,
    capital_expenditure: Any,
    *,
    expected: Any,
    tolerance: float = 0.01,
) -> DualCheck:
    """Dual implementation: EcoQuant's OCF - |CapEx| vs the kit's Decimal calc.

    Pass iff both agree with each other AND (when expected is given) with the
    expected value within tolerance.
    """
    from financial_systems_verification.models import (
        CashFlowProxyInput,
        FinanceCase,
        Formula,
    )
    from financial_systems_verification.finance import calculate_case

    ocf = float(operating_cash_flow)
    capex = float(capital_expenditure)
    ecoquant_result = ocf - abs(capex)

    case = FinanceCase(
        case_id="dual-ocf-capex",
        formula=Formula.CASHFLOW_PROXY,
        description="FinVEST dual-implementation check",
        inputs=CashFlowProxyInput(
            kind="cashflow-proxy",
            operating_cash_flow=_dec_str(ocf),
            capital_expenditure=_dec_str(abs(capex)),
            currency="USD",
        ),
        expected={"cashflow_proxy": _dec_str(abs(ecoquant_result))},
        tolerance=_dec_str(tolerance),
        source_note="FinVEST evidence verification",
        synthetic=True,
    )
    kit_result = float(calculate_case(case)["cashflow_proxy"])

    agree = abs(ecoquant_result - kit_result) / max(1.0, abs(ecoquant_result)) <= tolerance
    if expected is not None:
        exp = float(expected)
        agree = agree and abs(ecoquant_result - exp) / max(1.0, abs(exp)) <= tolerance

    return DualCheck(
        passed=bool(agree),
        ecoquant_result=ecoquant_result,
        kit_result=_dec_str(kit_result),
        reason="dual implementation agree" if agree else "dual implementation mismatch",
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-") or "cfp"


def generate_mutation_challenges(
    *,
    operating_cash_flow: Any,
    capital_expenditure: Any,
    expected: Any,
) -> list[dict[str, Any]]:
    """Generate 8 mutation families of a correct cash-flow-proxy case.

    Each mutation changes ONE verifier-relevant property so a verifier that
    only passes correct cases (near-100%) is exposed. Expected verdict is
    ``REVIEW_REQUIRED`` for every mutation (the verifier must REJECT them).
    """
    from financial_systems_verification.models import (
        CashFlowProxyInput,
        FinanceCase,
        Formula,
    )

    ocf = float(operating_cash_flow)
    capex = float(abs(capital_expenditure))
    exp = float(expected)
    mutations: list[dict[str, Any]] = []

    def _case(ocf_v: float, capex_v: float, tag: str) -> dict[str, Any]:
        result = ocf_v - capex_v
        return {
            "mutation": tag,
            "expected_verdict": "REVIEW_REQUIRED",
            "inputs": {"operating_cash_flow": ocf_v, "capital_expenditure": capex_v},
            "computed": result,
            "correct_expected": exp,
            "would_pass": abs(result - exp) / max(1.0, abs(exp)) <= 0.01,
        }

    # 1. wrong sign: CapEx added instead of subtracted.
    mutations.append(_case(ocf, -capex, "wrong-sign"))
    # 2. scale x1000.
    mutations.append(_case(ocf * 1000, capex * 1000, "scale-x1000"))
    # 3. USD vs millions (x1000000 on both).
    mutations.append(_case(ocf / 1_000_000, capex / 1_000_000, "usd-vs-millions"))
    # 4. wrong fiscal year (different period value) — approximated by swapped values.
    mutations.append(_case(capex, ocf, "swapped-numerator-denominator"))
    # 5. stale filing (use an older CapEx value that no longer matches).
    mutations.append(_case(ocf, capex * 0.5, "stale-filing"))
    # 6. future source (use a CapEx value from a later period).
    mutations.append(_case(ocf, capex * 1.5, "future-source"))
    # 7. amendment mismatch (use the pre-amendment OCF).
    mutations.append(_case(ocf * 0.9, capex, "amendment-mismatch"))
    # 8. unit scale confusion (only OCF scaled).
    mutations.append(_case(ocf / 1000, capex, "unit-scale-mismatch"))

    return mutations


def mutation_report(mutations: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize which mutations would falsely pass a naive verifier."""
    would_pass = [m for m in mutations if m["would_pass"]]
    return {
        "total_mutations": len(mutations),
        "rejected_by_correct_verifier": len(mutations) - len(would_pass),
        "false_pass_risk": len(would_pass),
        "mutation_tags": [m["mutation"] for m in mutations],
        "note": (
            "A correct verifier must reject ALL mutations (expected_verdict "
            "REVIEW_REQUIRED). Any would_pass=True indicates the verifier "
            "cannot distinguish the mutation from the correct answer."
        ),
    }
