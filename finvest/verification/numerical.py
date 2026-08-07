"""FinVEST executable numerical verification (A3/A5).

End-to-end pipeline (no gold cells): question -> table retrieval -> row/column
selection -> cell extraction -> formula selection -> deterministic execution
-> answer verification. Reuses the E2 deterministic calculator for the
execution step; adds table/cell localization so the pipeline runs without gold
coordinates (the old E2 94% result used gold cells and is an oracle bound).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ecoquant.research.table_eval.calculate import calculate, extract_cells, header_years_for, parse_cell


@dataclass(frozen=True)
class NumericalVerification:
    """Result of executable numerical verification."""

    executable: bool
    result: float | None
    verification_state: str  # SUPPORTED | INSUFFICIENT_EVIDENCE | REVIEW_REQUIRED
    reason: str | None = None


def verify_calculation(
    *,
    operation: str,
    evidence_texts: tuple[str, ...],
    expected_value: float | None,
    tolerance: float = 0.01,
    required_concepts: set[str] | None = None,
) -> NumericalVerification:
    """Verify a derived answer is reproducible from the evidence.

    Extracts numbers from the evidence texts (scale-normalized via the E2
    parser), applies the operation, and checks the result against the expected
    value within tolerance.

    N-8: when ``required_concepts`` is given (the calculation program's input
    concepts), the evidence must contain every one of them. Without this, a
    subtract over a pool that only contains OCF values (capex missing) computed
    a nonsense negative that was marked SUPPORTED under the executability-only
    check and routed to ANSWER with zero gold recall.
    """
    values = _extract_numbers(evidence_texts)
    if required_concepts:
        present = {_concept_of(text) for text in evidence_texts}
        missing = required_concepts - present
        if missing:
            return NumericalVerification(
                False, None, "REVIEW_REQUIRED",
                f"missing required input concept(s): {sorted(missing)}",
            )
    if not values:
        return NumericalVerification(False, None, "INSUFFICIENT_EVIDENCE", "no numeric evidence")
    try:
        result = calculate(operation, values)
    except (ValueError, ZeroDivisionError) as exc:
        return NumericalVerification(False, None, "REVIEW_REQUIRED", f"calc failed: {exc}")
    if expected_value is None:
        return NumericalVerification(True, result, "SUPPORTED", "executed, no gold to check")
    if abs(result - expected_value) / max(1.0, abs(expected_value)) <= tolerance:
        return NumericalVerification(True, result, "SUPPORTED", "matches gold within tolerance")
    return NumericalVerification(True, result, "REVIEW_REQUIRED", "mismatch vs gold")


def locate_cells(
    table_text: str,
    metric_hint: str,
    year_hint: str | None = None,
) -> tuple[int, int] | None:
    """Locate (row, col) for a metric in a serialized table (no gold coords).

    Heuristic: find the row whose label contains the metric hint; find the
    column whose header contains the year (or the first numeric column).
    """
    rows = [row.split(" | ") for row in table_text.split("\n") if row.strip()]
    if not rows:
        return None
    header = rows[0]
    for row_idx, row in enumerate(rows[1:], start=1):
        if row and metric_hint.lower() in row[0].lower():
            for col_idx, cell in enumerate(header):
                if year_hint and year_hint in cell:
                    return row_idx, col_idx
            # Fall back to first numeric column after the label.
            for col_idx in range(1, len(row)):
                if parse_cell(row[col_idx]) is not None:
                    return row_idx, col_idx
    return None


def _concept_of(text: str) -> str | None:
    """First token of a corpus text span is the XBRL concept name.

    Corpus spans are built as '{concept} {value} {unit} {start} {end} {filed}
    {form} {accession}', so the concept is the leading token. Returns None for
    spans that do not start with an alphanumeric identifier.
    """
    import re

    m = re.match(r"^([A-Za-z0-9_]+)", text.strip())
    return m.group(1) if m else None


def _extract_numbers(texts: tuple[str, ...]) -> list[float]:
    """Extract the numeric VALUES from evidence text spans.

    N-7: raw regex extraction split ISO dates ('2024-09-29') into three
    numbers (2024, -9, -29) which then polluted arithmetic (e.g. subtract
    produced a nonsense negative that was still marked SUPPORTED under the
    executability-only check). This removes date-shaped and negative-in-
    date tokens before matching the value, then captures the remaining
    (optionally signed) decimals.
    """
    import re

    numbers: list[float] = []
    for text in texts:
        # Blank out date-shaped tokens first: YYYY-MM-DD / YYYY-MM-DDThh:mm:ss
        # (also their sub-tokens), so their digits never reach the value pool.
        text = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{1,2}(?::\d{1,2})?)?\b", " ", text)
        # Also drop bare signed numbers that are the pieces of a date already
        # glued by the corpus tokenizer (e.g. '-9' following a 4-digit year).
        text = re.sub(r"(?<=\b\d{4})-(\d{1,2})\b", r" \1", text)
        # Blank form-type markers (10-K / 10-Q / 8-K) whose '10'/'8' are not values.
        text = re.sub(r"\b\d{1,2}-[A-Z]\b", " ", text)
        numbers.extend(float(t) for t in re.findall(r"-?\d+(?:\.\d+)?", text))
    return numbers
