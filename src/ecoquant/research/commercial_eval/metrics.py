"""E7: deterministic commercial ratio calculators with honest no-conclusion.

Every calculator returns None when a required input is missing (no evidence),
zero denominator, or non-finite — never fabricating a value. The caller decides
how to label the result (fact vs inference) based on which inputs were direct
resolved facts vs proxies.
"""

from __future__ import annotations

import math
from typing import TypeAlias

Number: TypeAlias = float | int | None


def _valid(value: Number) -> bool:
    return value is not None and math.isfinite(float(value))


def gross_margin(gross_profit: Number, revenue: Number) -> float | None:
    """Gross profit / revenue. None if either missing or revenue is zero."""
    if not _valid(gross_profit) or not _valid(revenue) or float(revenue) == 0:
        return None
    return float(gross_profit) / float(revenue)


def operating_margin(operating_income: Number, revenue: Number) -> float | None:
    """Operating income / revenue."""
    if not _valid(operating_income) or not _valid(revenue) or float(revenue) == 0:
        return None
    return float(operating_income) / float(revenue)


def working_capital(current_assets: Number, current_liabilities: Number) -> float | None:
    """Current assets - current liabilities."""
    if not _valid(current_assets) or not _valid(current_liabilities):
        return None
    return float(current_assets) - float(current_liabilities)


def fcff(operating_cash_flow: Number, capex: Number) -> float | None:
    """Free cash flow to firm ≈ operating cash flow - capex."""
    if not _valid(operating_cash_flow) or not _valid(capex):
        return None
    return float(operating_cash_flow) - float(capex)


def roic(
    net_income: Number,
    *,
    equity: Number,
    total_debt: Number,
    cash: Number,
) -> float | None:
    """Return on invested capital ≈ net income / (equity + debt - cash)."""
    if not all(_valid(v) for v in (net_income, equity, total_debt, cash)):
        return None
    invested = float(equity) + float(total_debt) - float(cash)
    if invested == 0:
        return None
    return float(net_income) / invested


def reinvestment_rate(capex: Number, operating_cash_flow: Number) -> float | None:
    """Capex / operating cash flow (reinvestment intensity)."""
    if not _valid(capex) or not _valid(operating_cash_flow) or float(operating_cash_flow) == 0:
        return None
    return float(capex) / float(operating_cash_flow)


def debt_to_equity(total_debt: Number, equity: Number) -> float | None:
    """Total debt / equity (capital structure)."""
    if not _valid(total_debt) or not _valid(equity) or float(equity) == 0:
        return None
    return float(total_debt) / float(equity)
