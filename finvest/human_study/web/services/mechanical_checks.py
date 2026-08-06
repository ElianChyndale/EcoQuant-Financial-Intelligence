"""Neutral mechanical checks — objective facts, never decisions.

Each check returns a descriptive sentence. Forbidden wording: "Choose ABSTAIN",
"This case is OUTDATED", "The correct answer is...", "Use E01 and E03",
"The evidence is sufficient", "The system should REVIEW".
"""

from __future__ import annotations

from datetime import date, datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class MechanicalCheck:
    name: str
    ok: bool | None  # None = not applicable / insufficient info
    statement: str  # descriptive fact, never a recommendation


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def check_source_date_vs_cutoff(filing_date: object, source_cutoff: object) -> MechanicalCheck:
    filed = _parse_date(filing_date)
    cutoff = _parse_date(source_cutoff)
    if filed is None or cutoff is None:
        return MechanicalCheck("source_date_vs_cutoff", None,
                               "Source date or cutoff is not a parseable date.")
    days = (cutoff - filed).days
    if days < 0:
        return MechanicalCheck("source_date_vs_cutoff", False,
                               f"Evidence was filed {abs(days)} days AFTER the source cutoff.")
    return MechanicalCheck("source_date_vs_cutoff", True,
                           f"Evidence was filed {days} days before the source cutoff.")


def check_filing_type(document_version: object, expected: str = "10-K") -> MechanicalCheck:
    if document_version is None:
        return MechanicalCheck("filing_type", None, "Filing type is unknown.")
    if document_version == expected:
        return MechanicalCheck("filing_type", True, f"Filing type is {document_version}.")
    return MechanicalCheck("filing_type", False,
                           f"Filing type is {document_version}, not {expected}.")


def check_amended(document_version: object) -> MechanicalCheck:
    is_amended = str(document_version).endswith("/A")
    return MechanicalCheck(
        "amended", is_amended,
        "This evidence belongs to an amended filing (10-K/A, 10-Q/A)."
        if is_amended else "This evidence is from an original filing, not an amendment.",
    )


def check_scale_mismatch(evidence: list[dict]) -> MechanicalCheck:
    scales = {e.get("scale") for e in evidence if e.get("scale") is not None}
    units = {e.get("unit") for e in evidence if e.get("unit") is not None}
    if len(scales) > 1:
        return MechanicalCheck("scale", False,
                               f"Evidence items report different scales: {', '.join(sorted(scales))}.")
    if len(units) > 1:
        return MechanicalCheck("scale", False,
                               f"Evidence items report different units: {', '.join(sorted(units))}.")
    if len(scales) == 1:
        return MechanicalCheck("scale", True, f"All evidence items report scale {next(iter(scales))}.")
    return MechanicalCheck("scale", None, "Evidence scale is not reported.")


def check_period_mismatch(evidence: list[dict]) -> MechanicalCheck:
    periods = {e.get("valid_from") for e in evidence if e.get("valid_from") is not None}
    if len(periods) > 1:
        return MechanicalCheck("period", False,
                               f"Evidence items use different fiscal periods: {', '.join(sorted(str(p) for p in periods))}.")
    if len(periods) == 1:
        return MechanicalCheck("period", True, f"Evidence items share fiscal period {next(iter(periods))}.")
    return MechanicalCheck("period", None, "Evidence fiscal period is not reported.")


def check_issuer_consistency(evidence: list[dict], case_issuer: object) -> MechanicalCheck:
    issuers = {str(e.get("document_id", "")).split("-")[0] for e in evidence if e.get("document_id")}
    if len(issuers) > 1:
        return MechanicalCheck("issuer", False, f"Evidence spans multiple issuers: {', '.join(sorted(issuers))}.")
    if len(issuers) == 1 and case_issuer:
        match = next(iter(issuers)).upper() == str(case_issuer).upper()
        return MechanicalCheck("issuer", match,
                               f"Evidence issuer is {next(iter(issuers))}; case issuer is {case_issuer}.")
    return MechanicalCheck("issuer", None, "Evidence issuer is not determinable.")


def check_duplicate_evidence(evidence: list[dict]) -> MechanicalCheck:
    content_hashes = [e.get("content_hash") for e in evidence if e.get("content_hash")]
    if len(content_hashes) != len(set(content_hashes)):
        return MechanicalCheck("duplicate", False,
                               "Duplicate evidence items may be present (shared content hash).")
    return MechanicalCheck("duplicate", True, "No duplicate content hashes detected.")


def arithmetic_reproducible(inputs: list[float], operation: str, result: float, tolerance: float = 0.01) -> MechanicalCheck:
    """Deterministic arithmetic check; reports the mechanical result only."""
    try:
        if operation == "subtract":
            computed = inputs[0] - inputs[1]
        elif operation == "add":
            computed = sum(inputs)
        elif operation == "average":
            computed = sum(inputs) / len(inputs)
        else:
            return MechanicalCheck("arithmetic", None, f"Operation {operation!r} not supported by the check.")
    except (IndexError, ZeroDivisionError):
        return MechanicalCheck("arithmetic", None, "Arithmetic inputs are incomplete.")
    matches = abs(computed - result) <= max(1.0, abs(result)) * tolerance
    return MechanicalCheck(
        "arithmetic", matches,
        f"The arithmetic result from the displayed inputs is {computed:.3f} "
        f"({'matches' if matches else 'does not match'} the expected {result:.3f}).",
    )


def run_neutral_checks(
    evidence: list[dict],
    *,
    source_cutoff: object,
    case_issuer: object,
) -> list[MechanicalCheck]:
    """All descriptive checks for one case's evidence set."""
    checks = [
        check_source_date_vs_cutoff(evidence[0].get("filing_date"), source_cutoff) if evidence else
        MechanicalCheck("source_date_vs_cutoff", None, "No evidence to check."),
    ]
    for item in evidence:
        checks.append(check_filing_type(item.get("document_version")))
        checks.append(check_amended(item.get("document_version")))
    checks.append(check_scale_mismatch(evidence))
    checks.append(check_period_mismatch(evidence))
    checks.append(check_issuer_consistency(evidence, case_issuer))
    checks.append(check_duplicate_evidence(evidence))
    return checks
