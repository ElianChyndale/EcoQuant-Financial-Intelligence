"""E4: multi-layer claim verifier with four output states.

Verifies a claim against cited evidence through five layers:

1. ``citation_present`` — at least one evidence text is cited.
2. ``number_in_evidence`` — every claim number appears (approximately) in ≥1
   cited evidence.
3. ``year_consistent`` — the claimed year string appears in the evidence.
4. ``unit_scale_consistent`` — the claimed unit/scale string appears (if given).
5. ``calculation_reproducible`` — a supplied expected value matches the claim
   numbers (deterministic).
6. ``no_conflict`` — cited evidences do not contradict each other on the same
   metric (restatement semantics: differing values for the same key).

Output states:

- ``SUPPORTED`` — all applicable layers pass.
- ``REVIEW_REQUIRED`` — citation missing, or year/unit inconsistent.
- ``INSUFFICIENT_EVIDENCE`` — a claim number is not grounded in evidence.
- ``CONFLICTING_EVIDENCE`` — evidence texts disagree.

The false-pass rate (an unsupported claim marked SUPPORTED) is the critical
metric the benchmark measures; this verifier is deliberately conservative.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class ClaimInput:
    claim_text: str
    numbers: list[float]
    cited_evidence: list[str]
    expected_year: str | None = None
    expected_unit: str | None = None
    expected_scale: str | None = None
    expected_value: float | None = None


@dataclass(frozen=True)
class VerificationResult:
    state: str  # SUPPORTED | REVIEW_REQUIRED | INSUFFICIENT_EVIDENCE | CONFLICTING_EVIDENCE
    layer_results: dict[str, bool]
    reason: str | None = None


def _approx_in_text(value: float, text: str, tolerance: float = 1e-3) -> bool:
    """True if a number approximately appears in a text (handles units)."""
    for token in NUMBER_RE.findall(text):
        try:
            parsed = float(token)
        except ValueError:
            continue
        if math.isclose(parsed, value, rel_tol=tolerance, abs_tol=tolerance):
            return True
    return False


def verify_claim(claim: ClaimInput) -> VerificationResult:
    layers: dict[str, bool] = {}

    # 1. Citation present.
    layers["citation_present"] = bool(claim.cited_evidence)

    # 2. Every claim number grounded in ≥1 cited evidence.
    grounded = all(
        any(_approx_in_text(number, evidence) for evidence in claim.cited_evidence)
        for number in claim.numbers
    )
    layers["number_in_evidence"] = grounded

    # 3. Year consistency.
    if claim.expected_year is not None:
        layers["year_consistent"] = any(
            claim.expected_year in evidence for evidence in claim.cited_evidence
        )
    else:
        layers["year_consistent"] = True

    # 4. Unit/scale consistency.
    if claim.expected_unit is not None or claim.expected_scale is not None:
        joined = " ".join(claim.cited_evidence).lower()
        unit_ok = (
            claim.expected_unit is None or claim.expected_unit.lower() in joined
        )
        scale_ok = (
            claim.expected_scale is None or claim.expected_scale.lower() in joined
        )
        layers["unit_scale_consistent"] = unit_ok and scale_ok
    else:
        layers["unit_scale_consistent"] = True

    # 5. Calculation reproducible.
    if claim.expected_value is not None and claim.numbers:
        layers["calculation_reproducible"] = math.isclose(
            sum(claim.numbers) / len(claim.numbers),
            claim.expected_value,
            rel_tol=1e-6,
            abs_tol=1e-6,
        )
    else:
        layers["calculation_reproducible"] = True

    # 6. No conflict among cited evidences.
    layers["no_conflict"] = not _evidence_conflict(claim.cited_evidence)

    # State resolution (conservative: the most restrictive failing layer wins).
    if not layers["citation_present"]:
        return VerificationResult("REVIEW_REQUIRED", layers, "no citation")
    if not layers["number_in_evidence"]:
        return VerificationResult("INSUFFICIENT_EVIDENCE", layers, "claim number not grounded")
    if not layers["no_conflict"]:
        return VerificationResult("CONFLICTING_EVIDENCE", layers, "evidence conflict")
    if not layers["year_consistent"] or not layers["unit_scale_consistent"]:
        return VerificationResult("REVIEW_REQUIRED", layers, "year/unit/scale mismatch")
    if not layers["calculation_reproducible"]:
        return VerificationResult("REVIEW_REQUIRED", layers, "calculation not reproducible")
    return VerificationResult("SUPPORTED", layers)


def _evidence_conflict(evidence_texts: list[str]) -> bool:
    """Detect conflicting values across evidence texts (restatement semantics).

    If two evidence texts both mention a number of similar magnitude (within
    50%) but the numbers differ by >1%, treat as a conflict. Conservative:
    only flags clear disagreements.
    """
    numbers_by_text: list[list[float]] = []
    for text in evidence_texts:
        numbers_by_text.append(
            [float(token) for token in NUMBER_RE.findall(text) if token.count(".") <= 1]
        )
    for i in range(len(evidence_texts)):
        for j in range(i + 1, len(evidence_texts)):
            for a in numbers_by_text[i]:
                for b in numbers_by_text[j]:
                    if a == 0 or b == 0:
                        continue
                    if 0.5 < a / b < 2.0 and abs(a - b) / max(a, b) > 0.01:
                        return True  # same magnitude, differing values
    return False
