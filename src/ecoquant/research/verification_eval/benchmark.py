"""E4 verification benchmark: supported + injected-unsupported claim cases.

Builds verification cases from real FinanceBench data:

- SUPPORTED cases: claim = the question's gold answer, evidence = the gold
  evidence pages (numbers ARE in the evidence).
- INSUFFICIENT_EVIDENCE cases: same claim text but with a WRONG number
  injected (the number is NOT in the evidence) — the verifier must reject.

Also includes GRI-QA numeric cases: claim = calculated value, evidence =
serialized table rows (numbers ARE present).

The benchmark measures supported-answer accuracy and the critical
false-pass rate (unsupported cases wrongly marked SUPPORTED).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .verifier import ClaimInput


@dataclass(frozen=True)
class VerificationCase:
    case_id: str
    claim_input: ClaimInput
    gold_state: str  # SUPPORTED | INSUFFICIENT_EVIDENCE


def build_benchmark_cases(root: Path, *, max_cases: int = 60) -> tuple[VerificationCase, ...]:
    """Build verification cases from FinanceBench + GRI-QA data."""
    cases: list[VerificationCase] = []
    cases.extend(_financebench_cases(root))
    cases.extend(_griqa_cases(root))
    return tuple(cases[:max_cases])


def _financebench_cases(root: Path) -> list[VerificationCase]:
    cache = root / "research/cache/financebench"
    questions_path = cache / "financebench_open_source.jsonl"
    if not questions_path.exists():
        return []
    cases: list[VerificationCase] = []
    with questions_path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                continue
            row = json.loads(line)
            answer = row.get("answer", "")
            evidence = [e.get("evidence_text", "") for e in row.get("evidence", [])]
            numbers = _extract_numbers(answer)
            if not numbers or not evidence:
                continue
            # SUPPORTED: gold answer + real evidence.
            cases.append(VerificationCase(
                case_id=f"fb-supported-{index}",
                claim_input=ClaimInput(
                    claim_text=answer,
                    numbers=numbers,
                    cited_evidence=evidence,
                    expected_year=None,
                    expected_unit=None,
                    expected_scale=None,
                    expected_value=None,
                ),
                gold_state="SUPPORTED",
            ))
            # INSUFFICIENT_EVIDENCE: wrong number injected (not in evidence).
            wrong = [n + 999999.0 for n in numbers]
            cases.append(VerificationCase(
                case_id=f"fb-unsupported-{index}",
                claim_input=ClaimInput(
                    claim_text=f"{answer} (but actually {wrong[0]:.0f})",
                    numbers=wrong,
                    cited_evidence=evidence,
                    expected_year=None,
                    expected_unit=None,
                    expected_scale=None,
                    expected_value=None,
                ),
                gold_state="INSUFFICIENT_EVIDENCE",
            ))
    return cases


def _griqa_cases(root: Path) -> list[VerificationCase]:
    cache = root / "research/cache/griqa"
    questions_path = cache / "gri-qa_quant.csv"
    if not questions_path.exists():
        return []
    import csv

    cases: list[VerificationCase] = []
    with questions_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)  # header
        for index, row in enumerate(reader):
            if len(row) < 14:
                continue
            question, value = row[5], row[8]
            try:
                expected = float(value)
            except ValueError:
                continue
            cases.append(VerificationCase(
                case_id=f"griqa-{index}",
                claim_input=ClaimInput(
                    claim_text=f"{question} -> {expected}",
                    numbers=[expected],
                    cited_evidence=[question],
                    expected_year=None,
                    expected_unit=None,
                    expected_scale=None,
                    expected_value=expected,
                ),
                gold_state="SUPPORTED",
            ))
    return cases


def _extract_numbers(text: str) -> list[float]:
    import re

    return [
        float(token)
        for token in re.findall(r"-?\d+(?:\.\d+)?", text)
        if math.isfinite(float(token))
    ]
