"""Self-Contained Human Evidence Package (SHEP) builder (Phase 11).

ACCEPTANCE CRITERION: a case may only enter the annotation queue if a
researcher can make a judgement from a single page. That page must contain
the evidence as a human would read it, not as machine fields.

A SHEP contains:
  A. question + definition statement (plain language, explicit term mapping);
  B. original evidence table (rows with fiscal-year columns, units, source);
  C. independent calculation area (inputs shown SEPARATELY, no precomputed
     result — the machine candidate answer stays SEALED until the
     researcher's first-pass judgement is frozen, per policy rule 2);
  D. time & version card (target period vs filing dates, cutoff, amendments);
  E. machine fields in a collapsible technical section (never the primary
     display).

The reference result is NEVER included in the display package. The sealed
candidate lives in the manifest; practice mode reveals it only AFTER the
researcher submits their own judgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .human_readable import format_value, human_label, unit_label

# Human-readable operation names for calculation programs.
OPERATION_LABELS: dict[str, str] = {
    "subtract": "first input − second input (absolute value where the source "
                "reports a negative outflow)",
    "add": "first input + second input",
    "multiply": "first input × second input",
    "divide": "first input ÷ second input",
}

# Phrases that mark a definition as NOT settled (case must not be signed).
UNSETTLED_DEFINITION_MARKERS = (
    "to be confirmed", "confirm by the researcher", "tbd", "undefined",
)


def _contested(assumptions: tuple[str, ...]) -> bool:
    lowered = " ".join(assumptions).lower()
    return any(marker in lowered for marker in UNSETTLED_DEFINITION_MARKERS)


def _definition_statement(
    sealed_case: dict[str, Any] | None,
) -> tuple[str, bool, list[str]]:
    """Build a plain-language definition from the sealed case.

    Returns (statement, contested, assumptions). ``contested`` is True when
    the metric definition is not settled — such a case must be blocked from
    signing (a definition cannot be both 'to be confirmed' and pre-answered).
    """
    assumptions = list(sealed_case.get("assumptions") or [])
    program = sealed_case.get("calculation_program")
    if program:
        inputs = list(program.get("inputs") or [])
        op = program.get("operation", "")
        op_label = OPERATION_LABELS.get(op, f"operation '{op}'")
        statement = (
            f"本题按以下显式定义计算：{op_label}。"
            f"输入项分别为 {' 和 '.join(inputs) or '(无)'}。"
        )
        return statement, _contested(tuple(assumptions)), assumptions
    # Non-derived case: definition is the question's own terms.
    statement = "本题为直接提取/事实性问题；请按页面证据表与时间版本卡判断。"
    return statement, _contested(tuple(assumptions)), assumptions


def _period_key(record: Any) -> str:
    """Fiscal-year key for table columns from a resolved record.

    Uses the PERIOD's own year (end/start) — never the filing-context
    fiscal_year label, which can point at a LATER filing that merely shows
    this period as comparative figures.
    """
    end = getattr(record, "end", None)
    if end:
        return f"FY{str(end)[:4]}"
    start = getattr(record, "start", None)
    if start:
        return f"FY{str(start)[:4]}"
    return "—"


def _evidence_table(records: list[Any]) -> dict[str, Any]:
    """Group resolved evidence into a human-readable statement table."""
    rows: list[dict[str, Any]] = []
    for rec in records:
        if getattr(rec, "resolution_status", "") != "resolved":
            continue
        rows.append({
            "label": human_label(getattr(rec, "concept", None)),
            "value": format_value(getattr(rec, "value", None)),
            "unit": unit_label(getattr(rec, "unit", None)),
            "period": _period_key(rec),
            "form": getattr(rec, "form", None),
            "filing_date": str(getattr(rec, "filing_date", "") or ""),
            "accession": getattr(rec, "accession", None),
            "concept": getattr(rec, "concept", None),
        })
    return {
        "rows": rows,
        "source_footnote": "数值取自 SEC XBRL companyfacts（原始来源见时间版本卡）。",
    }


def _calculation_inputs(
    sealed_case: dict[str, Any] | None,
    records: list[Any],
) -> dict[str, Any]:
    """Independent calculation area: inputs ONLY, result stays sealed."""
    program = sealed_case.get("calculation_program") if sealed_case else None
    if not program:
        return {"operation": None, "inputs": [], "has_calculation": False}
    inputs: list[dict[str, Any]] = []
    for rec in records:
        if getattr(rec, "resolution_status", "") != "resolved":
            continue
        inputs.append({
            "label": human_label(getattr(rec, "concept", None)),
            "concept": getattr(rec, "concept", None),
            "value": format_value(getattr(rec, "value", None)),
            "raw_value": getattr(rec, "value", None),
            "unit": unit_label(getattr(rec, "unit", None)),
        })
    return {
        "operation": OPERATION_LABELS.get(program.get("operation", ""),
                                          program.get("operation", "")),
        "inputs": inputs,
        "has_calculation": True,
        "note": "请根据上方两个输入独立计算并填写结果；机器候选答案在提交前不会显示。",
    }


def _time_version_card(
    view: dict[str, Any],
    records: list[Any],
) -> dict[str, Any]:
    """Time & version card: target vs filing, cutoff, amendments."""
    target = view.get("target_period") or view.get("target_period_end")
    cutoff = view.get("source_cutoff")
    rows: list[dict[str, Any]] = []
    for rec in records:
        if getattr(rec, "resolution_status", "") != "resolved":
            continue
        filing = getattr(rec, "filing_date", None)
        end = getattr(rec, "end", None)
        after_target = False
        if filing and end:
            try:
                after_target = date.fromisoformat(str(filing)) > date.fromisoformat(str(end))
            except (ValueError, TypeError):
                after_target = None
        rows.append({
            "label": human_label(getattr(rec, "concept", None)),
            "period": f"{getattr(rec, 'start', '') or '—'} → {getattr(rec, 'end', '') or '—'}",
            "fiscal_year": getattr(rec, "fiscal_year", None),
            "filing_date": str(filing or ""),
            "form": getattr(rec, "form", None),
            "accession": getattr(rec, "accession", None),
            "amendment": getattr(rec, "amendment_status", None),
            "after_target": after_target,
        })
    return {
        "target_period": str(target or "—"),
        "source_cutoff": str(cutoff or "—"),
        "rows": rows,
        "note": (
            "若 filing date 晚于目标期结束日，需自行判断：后发 10-K 是否包含目标期 "
            "comparative figures，是否存在 amendment/restatement，以及是否应优先使用 "
            "更接近目标期的原始 filing。"
        ),
    }


def _raw_rows(records: list[Any]) -> list[dict[str, Any]]:
    """RAW source rows for verification: the exact companyfacts JSON row the
    resolver matched, so a researcher can verify the numbers independently.

    Each row is the verbatim source record (val/start/end/accn/filed/fy/fp/form)
    plus the file it came from and the file's sha256 — no transcription.
    """
    rows: list[dict[str, Any]] = []
    for rec in records:
        if getattr(rec, "resolution_status", "") != "resolved":
            continue
        rows.append({
            "concept": getattr(rec, "concept", None),
            "taxonomy": getattr(rec, "taxonomy", None),
            "val": getattr(rec, "value", None),
            "unit": getattr(rec, "unit", None),
            "start": str(getattr(rec, "start", "") or ""),
            "end": str(getattr(rec, "end", "") or ""),
            "fy": getattr(rec, "fiscal_year", None),
            "fp": getattr(rec, "fiscal_period", None),
            "form": getattr(rec, "form", None),
            "filed": str(getattr(rec, "filing_date", "") or ""),
            "accn": getattr(rec, "accession", None),
            "source_file": "research/cache/sec/{issuer}_companyfacts.json".format(
                issuer=(getattr(rec, "issuer", "") or "").lower()),
            "source_hash": getattr(rec, "source_hash", None),
        })
    return rows


def _machine_fields(records: list[Any]) -> list[dict[str, Any]]:
    """Technical details: full machine identity (collapsed section only)."""
    fields: list[dict[str, Any]] = []
    for rec in records:
        fields.append({
            "evidence_id": getattr(rec, "evidence_id", ""),
            "concept": getattr(rec, "concept", None),
            "taxonomy": getattr(rec, "taxonomy", None),
            "value": getattr(rec, "value", None),
            "unit": getattr(rec, "unit", None),
            "scale": getattr(rec, "scale", None),
            "scope": getattr(rec, "scope", None),
            "start": str(getattr(rec, "start", "") or ""),
            "end": str(getattr(rec, "end", "") or ""),
            "fiscal_year": getattr(rec, "fiscal_year", None),
            "fiscal_period": getattr(rec, "fiscal_period", None),
            "form": getattr(rec, "form", None),
            "filing_date": str(getattr(rec, "filing_date", "") or ""),
            "accession": getattr(rec, "accession", None),
            "content_hash": getattr(rec, "content_hash", None),
            "amendment_status": getattr(rec, "amendment_status", None),
            "resolution_status": getattr(rec, "resolution_status", None),
        })
    return fields


def build_evidence_package(
    view: dict[str, Any],
    resolved: list[Any],
    sealed_case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Self-Contained Human Evidence Package for one case view.

    ``view`` is the display-safe projection (question/issuer/cutoff/target/
    evidence descriptors). ``resolved`` are the resolver records. ``sealed_case``
    is the sealed manifest case (server-side only) — used for the definition
    statement and calculation inputs; its candidate RESULT is never included.
    """
    definition, contested, assumptions = _definition_statement(sealed_case)
    return {
        "question": view.get("question", ""),
        "issuer": view.get("issuer"),
        "definition": {
            "statement": definition,
            "contested": contested,
            "assumptions": assumptions,
        },
        "evidence_table": _evidence_table(resolved),
        "raw_rows": _raw_rows(resolved),  # VERIFICATION GATE: raw source rows
        "calculation": _calculation_inputs(sealed_case, resolved),
        "time_version": _time_version_card(view, resolved),
        "machine": _machine_fields(resolved),
    }


@dataclass(frozen=True)
class PackageGate:
    """Preflight gate on the SHEP: can this case be judged from one page?"""

    signable: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"signable": self.signable, "reasons": list(self.reasons)}


def package_gate(package: dict[str, Any]) -> PackageGate:
    """Acceptance check: no case enters the annotation queue without a SHEP
    that supports independent judgement.

    Blocks when:
    - the metric definition is unsettled ('to be confirmed' style), or
    - evidence is missing or unresolved (nothing to read), or
    - the calculation area is incomplete (inputs missing).
    """
    reasons: list[str] = []
    if package["definition"]["contested"]:
        reasons.append("definition_unsettled")
    if not package["evidence_table"]["rows"]:
        reasons.append("no_human_readable_evidence")
    if package["calculation"]["has_calculation"] and not package["calculation"]["inputs"]:
        reasons.append("calculation_inputs_missing")
    return PackageGate(signable=not reasons, reasons=tuple(reasons))
