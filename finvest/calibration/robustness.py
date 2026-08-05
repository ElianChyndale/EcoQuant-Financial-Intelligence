"""FinVEST robustness paired perturbations (A7).

Each case is expanded into paired perturbations that preserve a mapping to the
unperturbed base. Report paired effect sizes + clustered CIs — never just the
mean.

Perturbations: query paraphrase, issuer swap, fiscal-year swap, currency/scale
swap, table row shuffle, page-order shuffle, OCR deletion, OCR number
corruption, duplicate evidence, missing evidence, long-distractor injection,
amendment/original swap, footnote removal, chart-only evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PERTURBATIONS = (
    "query_paraphrase", "issuer_swap", "fiscal_year_swap", "currency_scale_swap",
    "table_row_shuffle", "page_order_shuffle", "ocr_deletion",
    "ocr_number_corruption", "duplicate_evidence", "missing_evidence",
    "long_distractor_injection", "amendment_original_swap", "footnote_removal",
    "chart_only_evidence",
)


@dataclass(frozen=True)
class PerturbedCase:
    base_case_id: str
    perturbation: str
    question: str
    evidence: tuple[str, ...]


def apply_perturbation(
    *,
    base_case_id: str,
    question: str,
    evidence: tuple[str, ...],
    perturbation: str,
) -> PerturbedCase:
    """Apply one paired perturbation, preserving the base mapping."""
    if perturbation == "query_paraphrase":
        question = f"Could you tell me {question[0].lower()}{question[1:]}"
    elif perturbation == "issuer_swap":
        question = re.sub(r"\b(AAPL|MSFT|KO|EQIX|JNJ|UPS)\b", "OTHERCO", question, flags=re.IGNORECASE)
    elif perturbation == "fiscal_year_swap":
        question = re.sub(r"(20\d{2})", lambda m: str(int(m.group(1)) - 1), question)
    elif perturbation == "currency_scale_swap":
        evidence = tuple(e.replace("billion", "million") for e in evidence)
    elif perturbation == "table_row_shuffle":
        rows = evidence[0].split("\n") if evidence else []
        if len(rows) > 2:
            evidence = ("\n".join([rows[0]] + rows[2:] + [rows[1]]),)
    elif perturbation == "page_order_shuffle":
        evidence = tuple(reversed(evidence))
    elif perturbation == "ocr_deletion":
        evidence = tuple(re.sub(r"\d", "", e) for e in evidence)
    elif perturbation == "ocr_number_corruption":
        evidence = tuple(
            re.sub(r"(\d)", lambda m: {"0": "8", "1": "7", "3": "8"}.get(m.group(1), m.group(1)), e)
            for e in evidence
        )
    elif perturbation == "duplicate_evidence":
        evidence = evidence + evidence[:1] if evidence else evidence
    elif perturbation == "missing_evidence":
        evidence = evidence[1:] if len(evidence) > 1 else ()
    elif perturbation == "long_distractor_injection":
        evidence = evidence + ("Irrelevant long passage about unrelated market conditions " * 20,)
    elif perturbation == "amendment_original_swap":
        evidence = tuple(e + " (original filing)" for e in evidence)
    elif perturbation == "footnote_removal":
        evidence = tuple(re.sub(r"\([^)]*\)", "", e) for e in evidence)
    elif perturbation == "chart_only_evidence":
        evidence = ("[CHART IMAGE: bar chart, values not machine-readable]",)
    else:
        raise ValueError(f"unknown perturbation: {perturbation}")
    return PerturbedCase(base_case_id, perturbation, question, evidence)


def paired_effect(
    base_score: float,
    perturbed_score: float,
) -> float:
    """Paired effect: perturbed - base (positive = degradation)."""
    return perturbed_score - base_score
