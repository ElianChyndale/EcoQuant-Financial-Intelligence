"""FinVEST program induction (P0-9).

Induces an executable symbolic program from a natural-language financial
question. The induced program (operation + required metric concepts) is what
the production verifier executes — the sealed benchmark payload's calc-program
field is NEVER consumed (it lives beside the hidden answer in the same payload,
so reading it would be oracle assistance).

Inputs used (all gold-free, all available to a real user at inference time):
  - the question text,
  - the public, versioned concept dictionary
    (finvest/retrieval/retrievers.py::CONCEPT_DICTIONARY) — maps natural
    language terms to XBRL concepts,
  - a public finance-operators lexicon aligned with the deterministic
    calculator's FUNCTIONS (src/ecoquant/research/table_eval/calculate.py).

Deterministic rule baseline first (P3 of the plan); a small fine-tuned model
is a later milestone and must respect the same gold-free contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from finvest.retrieval.retrievers import _concepts_for

# XBRL concepts used by the FCFF derivation rule (OCF - capex).
_OCF = "NetCashProvidedByUsedInOperatingActivities"
_CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"

# Finance operators: natural-language patterns -> executable operation name.
# Operation names MUST match calculate.FUNCTIONS
# (src/ecoquant/research/table_eval/calculate.py:24-27).
# Ordered: more specific patterns first (so 'free cash flow' matches the FCFF
# rule before the generic sum/plus patterns could).
_OPERATOR_LEXICON: tuple[tuple[str, str], ...] = (
    (r"\bminus\b|\bsubtract\b|\bdifference between\b|\bafter subtracting\b", "subtract"),
    (r"\bfree cash flow\b|\bfcff\b", "subtract"),  # FCFF = OCF - capex
    (r"\bsum\b|\btotal of\b|\bcombined\b|\bplus\b|\badded to\b", "sum"),
    (r"\baverage\b|\bmean\b", "average"),
    (r"\bincrease percentage\b|\bpercent(?:age)? increase\b", "increase_percentage"),
    (r"\breduction percentage\b|\bpercent(?:age)? (?:reduction|decrease)\b", "reduction_percentage"),
)

_ENTITY_RE = re.compile(
    r"\b(AAPL|MSFT|KO|EQIX|JNJ|UPS|Apple|Microsoft|Coca-Cola|Equinix|Johnson & Johnson)\b",
    re.IGNORECASE,
)
_FISCAL_YEAR_RE = re.compile(r"\b(?:fiscal\s+)?(?:fy)?(20\d{2})\b", re.IGNORECASE)
_FCFF_RE = re.compile(r"\bfree cash flow\b|\bfcff\b", re.IGNORECASE)


@dataclass(frozen=True)
class InducedProgram:
    """An executable symbolic program induced from a question (gold-free)."""

    operation: str | None  # None => extractive/unanswerable question (no program)
    required_metrics: tuple[str, ...]  # input concepts the evidence must contain
    entity: str | None = None
    period: str | None = None
    version_policy: str = "as-of-cutoff"
    source: str = "rule-lexicon"  # provenance of the induction
    confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "required_metrics": list(self.required_metrics),
            "entity": self.entity,
            "period": self.period,
            "version_policy": self.version_policy,
            "source": self.source,
            "confidence": self.confidence,
        }


def _detect_operation(question: str) -> tuple[str | None, str]:
    q = question.lower()
    for pattern, op in _OPERATOR_LEXICON:
        if re.search(pattern, q):
            return op, "rule-lexicon"
    return None, "no-operator"


def _confidence(question: str, operation: str | None, required: tuple[str, ...]) -> float:
    score = 0.0
    if operation:
        score += 0.4
    score += 0.2 * min(len(required), 3)
    return round(min(score, 1.0), 3)


def induce_program(question: str) -> InducedProgram:
    """Induce an executable program from a question. Only the question string is consumed.

    - entity / period: best-effort regex extraction (metadata only, never used
      in the executability decision).
    - operation: from the finance-operators lexicon (or the FCFF derivation
      rule).
    - required_metrics: XBRL concepts matched via the public concept dictionary;
      for the FCFF derivation they are the OCF + capex inputs explicitly.
    """
    if not question or not question.strip():
        return InducedProgram(None, (), source="empty-question")

    entity_match = _ENTITY_RE.search(question)
    entity = entity_match.group(1).upper() if entity_match else None
    year_match = _FISCAL_YEAR_RE.search(question)
    period = f"FY{year_match.group(1)}" if year_match else None

    operation, source = _detect_operation(question)

    if _FCFF_RE.search(question):
        required = (_OCF, _CAPEX)
        if operation is None:
            operation, source = "subtract", "fcff-derivation"
        else:
            source = "fcff-derivation"
    else:
        required = tuple(sorted(_concepts_for(question)))

    return InducedProgram(
        operation=operation,
        required_metrics=required,
        entity=entity,
        period=period,
        version_policy="as-of-cutoff",
        source=source,
        confidence=_confidence(question, operation, required),
    )
