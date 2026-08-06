"""Reference-case sheet generator (Phase 8, redesigned in Phase 11).

Produces candidate evidence sheets for reference cases. A sheet must be a
SELF-CONTAINED HUMAN EVIDENCE PACKAGE: a plain-language definition, the
evidence as a human-readable table (not XBRL tags), the calculation inputs
shown separately, and a time & version card.

The machine candidate decision/sufficiency is shown ONLY as a clearly
labelled CANDIDATE that the researcher must independently reproduce — it is
never presented as the answer. When the metric definition is unsettled, the
sheet says so and the case cannot be approved as gold.
"""

from __future__ import annotations

from pathlib import Path

from finvest.benchmark.builders.sec_cases import build_sec_cases
from finvest.human_study.web.services.evidence_package import (
    build_evidence_package,
    package_gate,
)
from finvest.human_study.web.services.evidence_service import resolve_evidence_set
from finvest.human_study.web.services.human_readable import format_value, human_label


def _case_view(case: object) -> dict:
    """Display-safe projection of a builder case (matches the CLI projection)."""
    target = getattr(case, "target_fiscal_year", None) or getattr(case, "target_period_end", None)
    return {
        "case_id": case.case_id,
        "question": case.question,
        "issuer": case.issuer_id,
        "source_cutoff": str(getattr(case, "source_cutoff", "") or ""),
        "target_period": str(target or ""),
        "evidence": [
            {
                "evidence_id": ev.evidence_id,
                "document_id": ev.document_id,
                "document_version": ev.document_version,
                "filing_date": str(ev.filing_date),
                "valid_from": str(ev.valid_from),
                "concept": ev.concept,
                "unit": ev.unit,
                "scale": ev.scale,
                "scope": ev.scope,
            }
            for ev in getattr(case, "evidence_items", ())
        ],
    }


def build_reference_sheet(case: object, *, cache_dir: Path, ticker: str) -> dict:
    """Build one candidate reference sheet (SHEP + machine candidate)."""
    view = _case_view(case)
    resolved = resolve_evidence_set(view["evidence"], cache_dir)
    sealed = {
        "calculation_program": (
            case.calculation_program.__dict__
            if getattr(case, "calculation_program", None) is not None else None
        ),
        "assumptions": list(getattr(case, "assumptions", ()) or ()),
    }
    package = build_evidence_package(view, resolved, sealed_case=sealed)
    gate = package_gate(package)
    return {
        "case_id": case.case_id,
        "status": "CANDIDATE_UNREVIEWED",
        "package": package,
        "gate": gate.as_dict(),
        # Machine candidate — labelled as such, never the researcher's answer.
        "machine_candidate": {
            "decision": getattr(case, "decision_label", None),
            "sufficiency": getattr(case, "sufficiency_label", None),
            "note": "机器候选判定。研究者必须独立重算并与本候选对照后才能接受。",
        },
        "researcher_review_fields": {
            "understand_question": None,
            "found_original_source": None,
            "agree_metric_definition": None,
            "agree_period": None,
            "agree_unit": None,
            "can_recompute_answer": None,
            "minimal_evidence_sufficient": None,
            "ambiguous": None,
        },
    }


def generate_reference_sheets(
    cache_dir: Path, out_dir: Path, *, tickers: tuple[str, ...], limit: int = 10
) -> list[dict]:
    """Generate up to `limit` candidate reference sheets from the v0.2 builder."""
    built = build_sec_cases(cache_dir, tickers=tickers)
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    ordered = sorted(built.cases, key=lambda c: (c.answer_type == "unanswerable", c.case_id))
    for case in ordered[:limit]:
        sheet = build_reference_sheet(case, cache_dir=cache_dir, ticker=case.issuer_id)
        (out_dir / f"{case.case_id}.md").write_text(
            _render_markdown(sheet), encoding="utf-8",
        )
        sheets.append(sheet)
    return sheets


def _render_markdown(sheet: dict) -> str:
    pkg = sheet["package"]
    lines = [
        f"# Reference Case (CANDIDATE): {sheet['case_id']}",
        "",
        f"**Status:** {sheet['status']}",
        "",
        "## Question",
        pkg["question"],
        "",
        "## Metric definition (explicit)",
        pkg["definition"]["statement"],
    ]
    if pkg["definition"]["contested"]:
        lines += ["", "**⚠ 定义未定稿（contested）——本 case 不得签署为 gold。**"]
    if pkg["definition"]["assumptions"]:
        lines += ["", "**Assumptions:**"]
        lines += [f"- {a}" for a in pkg["definition"]["assumptions"]]

    lines += ["", "## Original evidence table", ""]
    rows = pkg["evidence_table"]["rows"]
    if rows:
        lines.append("| Row | Value | Unit | Period | Source (form · filed · accn) |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            src = f"{r['form']} · {r['filing_date']} · {r['accession'] or '—'}"
            lines.append(f"| {r['label']} | {r['value']} | {r['unit']} | {r['period']} | {src} |")
    else:
        lines.append("_无已解析证据（无法从单页判断）。_")
    lines += ["", pkg["evidence_table"]["source_footnote"]]

    lines += ["", "## Independent calculation (inputs only — recompute yourself)", ""]
    calc = pkg["calculation"]
    if calc["has_calculation"]:
        lines.append(f"**Operation:** {calc['operation']}")
        for inp in calc["inputs"]:
            lines.append(f"- {inp['label']} = {inp['value']} {inp['unit']}")
        lines.append(f"*{calc['note']}*")
    else:
        lines.append("_本 case 无计算程序（直接提取/事实性问题）。_")

    lines += ["", "## Time & version card", ""]
    tv = pkg["time_version"]
    lines.append(f"- Target period: {tv['target_period']}")
    lines.append(f"- Source cutoff: {tv['source_cutoff']}")
    for r in tv["rows"]:
        after = "是" if r["after_target"] else ("否" if r["after_target"] is False else "?")
        lines.append(
            f"- {r['label']}: {r['period']} · filed {r['filing_date']} ({r['form']}) · "
            f"accn {r['accession'] or '—'} · after-target={after} · {r['amendment'] or '—'}"
        )
    lines.append(f"*{tv['note']}*")

    cand = sheet["machine_candidate"]
    lines += ["", "## Machine candidate (NOT the researcher's answer)",
              f"- Decision: **{cand['decision']}** · Sufficiency: **{cand['sufficiency']}**",
              f"- {cand['note']}", ""]

    lines += ["", "## Researcher review (candidate)",
              "- [ ] I understand the question",
              "- [ ] I found the original source",
              "- [ ] I agree the metric definition",
              "- [ ] I agree the period",
              "- [ ] I agree the unit",
              "- [ ] I recomputed the answer independently and it matches",
              "- [ ] The minimal evidence is sufficient",
              "- [ ] No ambiguity found", "",
              "*Candidate sheet prepared by AI. Researcher approval required before use as gold.*",
              ]
    return "\n".join(lines)
