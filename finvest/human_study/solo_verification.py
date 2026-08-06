"""Machine verification AFTER the human judgement is submitted (Stage 3).

Runs only after the solo annotator commits their answer (avoids anchoring
bias). Checks: accession, source hash, XBRL uniqueness, issuer, period,
unit/scale, filing-date vs cutoff, amendment, calculation, and that the
machine-extracted values match the displayed page values. Reports only the
DIFFERENCES — never overrides the human label.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class VerificationResult:
    checks: dict[str, Any]
    mismatches: tuple[str, ...]
    calc_match: bool | None  # None when no human answer to compare

    def as_dict(self) -> dict[str, Any]:
        return {
            "checks": self.checks,
            "mismatches": list(self.mismatches),
            "calc_match": self.calc_match,
            "status": "MATCH" if not self.mismatches and self.calc_match is not False else (
                "MISMATCH" if self.mismatches or self.calc_match is False else "NO_HUMAN_ANSWER"),
        }


def verify_annotation(
    *,
    raw_rows: list[dict[str, Any]],
    human_answer: Any,
    human_route: str,
    source_cutoff: str | None,
    target_period_end: str | None,
    displayed_values: dict[str, Any] | None = None,
    case_type: str | None = None,
) -> VerificationResult:
    """Run machine checks against the raw source rows and the human answer.

    ``case_type``: "derived" (OCF-capex, default) | "amended" (version case) |
    "insufficient" (negative case) | "extractive" (direct value).
    Amended/extractive cases EXPECT multiple accessions, an amendment, and
    duplicate concepts — those are reported in ``checks`` as facts but are NOT
    mismatches for that case type.
    """
    checks: dict[str, Any] = {}
    mismatches: list[str] = []
    case_type = case_type or ("amended" if any(
        str(r.get("form", "")).endswith("/A") for r in raw_rows) else "derived")

    # 1. Accession present and consistent across rows.
    accns = {r.get("accn") for r in raw_rows if r.get("accn")}
    checks["accession"] = sorted(a for a in accns if a)
    if len(accns) > 1 and case_type != "amended":
        mismatches.append("multiple_accessions")

    # 2. Source hash present per row.
    hashes = {r.get("source_hash") for r in raw_rows if r.get("source_hash")}
    checks["source_hashes"] = len(hashes)
    if not hashes:
        mismatches.append("missing_source_hash")

    # 3. Issuer consistent.
    issuers = {r.get("issuer") for r in raw_rows if r.get("issuer")}
    checks["issuers"] = sorted(issuers)
    if len(issuers) > 1:
        mismatches.append("multiple_issuers")

    # 4. Period consistency: all rows same start/end.
    periods = {(r.get("start"), r.get("end")) for r in raw_rows}
    checks["periods"] = sorted((str(s), str(e)) for s, e in periods if s and e)
    if len(periods) > 1:
        mismatches.append("multiple_periods")

    # 5. Target period matches fact period end.
    #    ``target_period_end`` may be a fiscal-year label (FY2024), a bare year
    #    (2008), or an ISO date (2024-09-28). Compare on the YEAR for labels.
    if target_period_end:
        fact_ends = {r.get("end") for r in raw_rows if r.get("end")}
        if fact_ends:
            target = str(target_period_end)
            fact_years = {str(e)[:4] for e in fact_ends}
            if target.startswith("FY"):
                target_year = target[2:]
            elif len(target) == 4 and target.isdigit():
                target_year = target
            else:
                target_year = None
            if target_year is not None:
                if target_year not in fact_years:
                    mismatches.append(
                        f"period_mismatch: target {target_period_end} vs facts {sorted(fact_ends)}"
                    )
            elif target not in fact_ends:
                mismatches.append(
                    f"period_mismatch: target {target_period_end} vs facts {sorted(fact_ends)}"
                )

    # 6. Unit consistency.
    units = {r.get("unit") for r in raw_rows if r.get("unit")}
    checks["units"] = sorted(units)
    if len(units) > 1:
        mismatches.append("multiple_units")

    # 7. Filing date vs source cutoff.
    if source_cutoff:
        try:
            cutoff = date.fromisoformat(str(source_cutoff)[:10])
        except (ValueError, TypeError):
            cutoff = None
        if cutoff:
            for r in raw_rows:
                filed = r.get("filed")
                if filed:
                    try:
                        fd = date.fromisoformat(str(filed)[:10])
                    except (ValueError, TypeError):
                        continue
                    if fd > cutoff:
                        checks["filing_after_cutoff"] = checks.get("filing_after_cutoff", 0) + 1

    # 8. Amendment detection.
    amended = [r for r in raw_rows if str(r.get("form", "")).endswith("/A")]
    checks["amendment"] = "AMENDED" if amended else "ORIGINAL"
    if amended and case_type != "amended":
        mismatches.append("amended_filing")

    # 9. XBRL fact uniqueness: one row per concept.
    concepts = [r.get("concept") for r in raw_rows]
    checks["concept_count"] = len(concepts)
    if len(set(concepts)) != len(concepts) and case_type != "amended":
        mismatches.append("duplicate_concept")

    # 10. Calculation check — only for derived cases with a machine formula.
    calc_match: bool | None = None
    if case_type == "derived" and human_answer is not None and human_answer != "":
        try:
            human_num = float(str(human_answer).replace(",", "").replace(" ", ""))
            machine_num = _machine_calc(raw_rows)
            calc_match = machine_num is not None and abs(human_num - machine_num) < 1.0
            if machine_num is not None:
                checks["machine_calculation"] = machine_num
                checks["human_calculation"] = human_num
            if calc_match is False:
                mismatches.append("calculation_mismatch")
        except (ValueError, TypeError):
            calc_match = None
    else:
        # For amended/extractive cases, the answer is a direct extracted value:
        # verify it equals one of the raw row values (amended row preferred).
        if human_answer is not None and human_answer != "":
            try:
                human_num = float(str(human_answer).replace(",", "").replace(" ", ""))
                vals = [r.get("val") for r in raw_rows]
                calc_match = human_num in vals
                checks["extracted_value"] = human_num
                checks["raw_values"] = vals
                if not calc_match:
                    mismatches.append("value_not_in_source")
            except (ValueError, TypeError):
                calc_match = None

    # 11. Displayed values match raw rows (page transcription integrity).
    if displayed_values:
        for concept, shown in displayed_values.items():
            raw_vals = {r.get("val") for r in raw_rows if r.get("concept") == concept}
            if raw_vals and shown not in raw_vals:
                mismatches.append(f"display_mismatch:{concept}")

    return VerificationResult(checks=checks, mismatches=tuple(mismatches), calc_match=calc_match)


def _machine_calc(raw_rows: list[dict[str, Any]]) -> float | None:
    """Machine calculation: OCF - capex (simplified proxy)."""
    ocf = capex = None
    for r in raw_rows:
        c = r.get("concept", "")
        if c == "NetCashProvidedByUsedInOperatingActivities":
            ocf = r.get("val")
        elif c == "PaymentsToAcquirePropertyPlantAndEquipment":
            capex = r.get("val")
    if ocf is None or capex is None:
        return None
    return float(ocf) - abs(float(capex))


def render_diff_report(result: VerificationResult) -> str:
    """Human-readable difference report (only diffs + status)."""
    lines = [f"Status: {result.as_dict()['status']}"]
    if result.checks.get("machine_calculation") is not None:
        lines.append(
            f"Human answer: {result.checks.get('human_calculation'):,.0f} · "
            f"Machine calculation: {result.checks.get('machine_calculation'):,.0f}"
        )
    for m in result.mismatches:
        lines.append(f"⚠ {m}")
    if not result.mismatches and result.calc_match is not False:
        lines.append("All machine checks passed (no differences found).")
    return "\n".join(lines)
