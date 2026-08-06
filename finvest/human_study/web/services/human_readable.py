"""Human-readable presentation layer for XBRL concepts (Phase 11).

Raw XBRL concept tags (``NetCashProvidedByUsedInOperatingActivities``) are
machine identifiers. Researchers read financial statements, not tags. This
module maps concepts to the labels a real statement uses, and formats units
the way a report does.

The mapping is EXHAUSTIVE-ONLY for known concepts; unknown concepts fall
back to the raw tag so nothing is ever silently mislabelled.
"""

from __future__ import annotations

CONCEPT_LABELS: dict[str, str] = {
    # Cash flow statement.
    "NetCashProvidedByUsedInOperatingActivities":
        "Net cash provided by operating activities",
    "PaymentsToAcquirePropertyPlantAndEquipment":
        "Payments for acquisition of property, plant and equipment",
    # Balance sheet.
    "Assets": "Total assets",
    "Liabilities": "Total liabilities",
    "StockholdersEquity": "Total stockholders' equity",
    "AccruedLiabilitiesCurrent": "Accrued liabilities, current",
    "EntityPublicFloat": "Entity public float",
    # Income statement.
    "Revenues": "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax":
        "Revenue from contracts with customers (excl. assessed tax)",
    "OperatingIncomeLoss": "Operating income (loss)",
    "NetIncomeLoss": "Net income (loss)",
    # Fixture-only concepts (synthetic data).
    "RevenueEur": "Revenues (reported in EUR)",
    "RevenueOld": "Revenues (prior fiscal year)",
    "DuplicateMetric": "Duplicate-metric fixture concept",
    "FutureExpense": "Future-filing fixture concept",
}

# Units a reader would recognise on a statement.
UNIT_LABELS: dict[str, str] = {
    "USD": "USD",
    "USD_Thousands": "USD thousands",
    "USD_Millions": "USD millions",
    "EUR": "EUR",
    "shares": "shares",
    "pure": "ratio",
}


def human_label(concept: str | None) -> str:
    """Human-readable statement label for a concept (raw tag if unknown)."""
    if not concept:
        return "—"
    return CONCEPT_LABELS.get(concept, concept)


def unit_label(unit: str | None) -> str:
    """Human-readable unit (raw unit if unknown)."""
    if not unit:
        return "—"
    return UNIT_LABELS.get(unit, unit)


def format_value(value: float | None, unit: str | None = None) -> str:
    """Format a fact value the way a financial statement does.

    Keeps full precision when the value is small; uses thousands separators
    for large figures. The unit is displayed separately by the caller.
    """
    if value is None:
        return "—"
    if abs(value) >= 1_000_000_000:
        return f"{value:,.0f}"
    if abs(value) >= 1_000:
        return f"{value:,.2f}"
    return f"{value:,.4f}"
