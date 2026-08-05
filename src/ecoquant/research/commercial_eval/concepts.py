"""E7: concept-resolution layer over SEC XBRL companyfacts.

Companies do not use identical GAAP concept names for the same metric (e.g.
revenue may be ``Revenues`` or ``RevenueFromContractWithCustomerExcludingAssessedTax``).
This layer tries an ordered list of aliases per metric, picks the annual 10-K
fact for the requested fiscal year, and returns a fully traceable
``ResolvedValue`` (value + concept + period_end + fact_id). When no alias has
evidence, it returns None — an honest "no conclusion without evidence".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ecoquant.research.temporal_eval.sec_adapter import SecBundle, SecFact

# Ordered alias lists per metric (first match with annual 10-K evidence wins).
METRIC_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "current_assets": (
        "AssetsCurrent",
        "CurrentAssets",
    ),
    "current_liabilities": (
        "LiabilitiesCurrent",
        "CurrentLiabilities",
    ),
    "inventory": ("InventoryNet", "InventoryFinishedGoodsNetOfReserves"),
    "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "total_debt": (
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtCurrent",
        "ConvertibleDebtCurrent",
    ),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "equity": ("StockholdersEquity",),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "OperatingCashFlowsContinuingOperations",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "interest_expense": ("InterestExpense", "InterestExpenseNonoperating"),
}


@dataclass(frozen=True)
class ResolvedValue:
    """One resolved annual fact for a metric, fully traceable."""

    value: float
    concept: str
    period_end: date
    fact_id: str
    form: str


def resolve_concept(
    bundle: SecBundle,
    ticker: str,
    metric: str,
    year: int,
) -> ResolvedValue | None:
    """Resolve a metric's annual 10-K value for a ticker/year, or None."""
    aliases = METRIC_CONCEPTS.get(metric)
    if aliases is None:
        return None
    candidates: list[ResolvedValue] = []
    for fact in bundle.facts:
        if fact.ticker != ticker or fact.form != "10-K":
            continue
        # Match by calendar year of the period end. Fiscal years vary by
        # company (Apple ends Sep, MSFT ends Jun, JNJ/UPS/KO end Dec); the
        # annual 10-K is the fact with the LATEST period end in that year, so
        # we keep all 10-K facts for the year and pick the latest end below.
        if fact.end.year != year:
            continue
        if fact.concept in aliases:
            candidates.append(ResolvedValue(
                value=fact.val,
                concept=fact.concept,
                period_end=fact.end,
                fact_id=fact.fact_id,
                form=fact.form,
            ))
    if not candidates:
        return None
    # Prefer the first alias in the ordered list that has evidence; among ties,
    # the latest period end wins (the annual report), then latest filed.
    for alias in aliases:
        matches = [c for c in candidates if c.concept == alias]
        if matches:
            return max(matches, key=lambda c: (c.period_end, c.fact_id))
    return max(candidates, key=lambda c: (c.period_end, c.fact_id))
