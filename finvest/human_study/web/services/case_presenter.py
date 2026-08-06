"""Conversational case presenter (Phase 12).

Presents a case for chat-based annotation WITH the verification gate: every
case shows the RAW source rows (verbatim companyfacts JSON + source file +
hash) BEFORE the human-readable interpretation, so the researcher can verify
numbers independently. No transcription-only display.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finvest.human_study.web.services.evidence_package import build_evidence_package
from finvest.human_study.web.services.evidence_service import resolve_evidence_set
from finvest.human_study.web.services.human_readable import format_value, human_label, unit_label


def load_manifest(day1_dir: Path) -> dict:
    return json.loads((day1_dir / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))


def base_cases(manifest: dict) -> list[dict]:
    from finvest.human_study.web.services.protocol_web import base_queue

    return base_queue(manifest)


def _case_view(sealed: dict) -> dict:
    """Display-safe projection (matches the CLI/web projection)."""
    target = sealed.get("target_fiscal_year") or sealed.get("target_period_end")
    return {
        "case_id": sealed["case_id"],
        "question": sealed["question"],
        "issuer": sealed["issuer_id"],
        "source_cutoff": sealed.get("source_cutoff"),
        "target_period": target,
        "evidence": sealed.get("evidence_items", []),
    }


def present_case(sealed: dict, cache: Path) -> dict[str, Any]:
    """Build the full conversational presentation of one sealed case.

    Includes: raw source rows (verification gate), human-readable table,
    definition, calculation inputs, time & version card.
    """
    view = _case_view(sealed)
    resolved = resolve_evidence_set(view["evidence"], cache)
    pkg = build_evidence_package(view, resolved, sealed_case=sealed)
    return {
        "case_id": sealed["case_id"],
        "question": sealed["question"],
        "definition": pkg["definition"],
        "raw_rows": pkg["raw_rows"],  # verification gate: verbatim source rows
        "evidence_table": pkg["evidence_table"],
        "calculation": pkg["calculation"],
        "time_version": pkg["time_version"],
        "gate": pkg.get("gate"),
    }


def present_from_manifest(day1_dir: Path, cache: Path, case_id: str) -> dict[str, Any]:
    """Read the manifest + SOURCE FILE, then present one case.

    This is the ONLY sanctioned entry point for conversational annotation:
    the source data is read from disk (research/cache/sec/*_companyfacts.json)
    at presentation time — never from memory or prior transcription.
    """
    manifest = load_manifest(day1_dir)
    cases = {c["case_id"]: c for c in base_cases(manifest)}
    if case_id not in cases:
        raise KeyError(f"case {case_id} not in manifest")
    return present_case(cases[case_id], cache)


def render_markdown(presented: dict[str, Any]) -> str:
    """Render the conversational presentation as readable markdown."""
    lines: list[str] = []
    lines.append(f"# Case: {presented['case_id']}")
    lines.append("")
    lines.append(f"**问题**：{presented['question']}")
    lines.append("")
    lines.append("## 指标定义（显式）")
    lines.append(presented["definition"]["statement"])
    for a in presented["definition"]["assumptions"]:
        lines.append(f"- 假设：{a}")
    if presented["definition"]["contested"]:
        lines.append("**⚠ 定义未定稿**")

    lines.append("")
    lines.append("## ① 原始 SEC 数据行（验证门禁——逐字来源，可独立核对）")
    lines.append("")
    rows = presented["raw_rows"]
    if rows:
        lines.append("```json")
        lines.append(json.dumps(rows, indent=2, default=str))
        lines.append("```")
        src = rows[0]
        lines.append(
            f"来源文件: {src.get('source_file')} · sha256: {str(src.get('source_hash'))[:16]}…"
        )
    else:
        lines.append("_无已解析证据（无法从单页判断）。_")

    lines.append("")
    lines.append("## ② 人类可读解读")
    lines.append("")
    for r in presented["evidence_table"]["rows"]:
        lines.append(
            f"- **{r['label']}**: {r['value']} {r['unit']} · {r['period']} · "
            f"{r['form']} · filed {r['filing_date']} · accn {r['accession'] or '—'}"
        )

    calc = presented["calculation"]
    if calc["has_calculation"]:
        lines.append("")
        lines.append("## ③ 独立计算区（输入已分开，请自行计算）")
        lines.append(f"**运算**：{calc['operation']}")
        for inp in calc["inputs"]:
            lines.append(f"- {inp['label']} = {inp['value']} {inp['unit']}")
        lines.append(f"*{calc['note']}*")

    tv = presented["time_version"]
    lines.append("")
    lines.append("## ④ 时间与版本卡")
    lines.append(f"- 目标期: {tv['target_period']} · source cutoff: {tv['source_cutoff']}")
    for r in tv["rows"]:
        after = "是" if r["after_target"] else ("否" if r["after_target"] is False else "?")
        lines.append(
            f"- {r['label']}: {r['period']} · filed {r['filing_date']} ({r['form']}) · "
            f"accn {r['accession'] or '—'} · 晚于目标期={after}"
        )
    lines.append(f"*{tv['note']}*")

    lines.append("")
    lines.append("## ⑤ Q4 判断对照表（每类检查：现状 + 你该看什么）")
    lines.append("")
    lines.append(_render_q4_checklist(presented))
    lines.append("")
    lines.append("**请回答 Q1-Q5 + 置信度。**")
    return "\n".join(lines)


def _render_q4_checklist(presented: dict[str, Any]) -> str:
    """Q4 issue checklist with the CURRENT STATE shown for each check.

    The researcher only marks a flag when the stated state is wrong or
    cannot be confirmed — they do not have to hunt for the facts.
    """
    tv = presented["time_version"]
    rows = tv.get("rows", [])
    calc = presented["calculation"]

    def periods_note() -> str:
        return "；".join(
            f"{r.get('label')}: {r.get('period')}" for r in rows
        ) or "—"

    def target_note() -> str:
        return str(tv.get("target_period") or "—")

    lines = [
        "| 检查项 | 页面当前状态 | 若下列为真则勾选 |",
        "|---|---|---|",
    ]
    # Wrong period
    lines.append(
        f"| **Wrong period** | 目标期 {target_note()}；证据期间 {periods_note()} | "
        "证据期间 ≠ 目标期间 |"
    )
    # Future source
    filings = [r.get("filing_date") for r in rows if r.get("filing_date")]
    after = any(r.get("after_target") for r in rows)
    lines.append(
        f"| **Future source** | filing 日期 {'晚于期间结束' if after else '在期间内或未知'} "
        f"({', '.join(filings) or '—'})；cutoff {str(tv.get('source_cutoff') or '—')} | "
        "filing 晚于 cutoff 或无法确认期间归属 |"
    )
    # Version / amendment
    forms = {r.get("form") for r in rows if r.get("form")}
    amendments = [r.get("form") for r in rows if str(r.get("form") or "").endswith("/A")]
    lines.append(
        f"| **Version/amendment unclear** | form {', '.join(sorted(forms)) or '—'}；"
        f"amendment {'存在: ' + ', '.join(amendments) if amendments else '未检出'} | "
        "存在 amendment/restatement 或版本关系不明 |"
    )
    # Metric definition
    contested = presented["definition"].get("contested", False)
    lines.append(
        f"| **Metric definition unclear** | 定义 {'已显式声明' if not contested else '未定稿(contested)'} | "
        "定义未定稿或概念映射(问题词汇→概念)不成立 |"
    )
    # Unit / scale
    units = {r.get("unit") for r in rows if r.get("unit")}
    lines.append(
        f"| **Unit/scale unclear** | 单位 {', '.join(sorted(units)) or '—'} | "
        "单位不一致或与问题要求不符 |"
    )
    # Wrong entity
    issuers = {r.get("issuer") for r in rows if r.get("issuer")}
    lines.append(
        f"| **Wrong entity** | issuer {', '.join(sorted(issuers)) or '—'} | "
        "issuer ≠ 问题主体 |"
    )
    # Calculation mismatch (only when inputs present)
    if calc.get("has_calculation") and calc.get("inputs"):
        lines.append(
            "| **Calculation mismatch** | 机器计算已隐藏(提交后核验)；输入见③ | "
            "你的计算与机器结果不一致(核验阶段才可知) |"
        )
    # Missing evidence
    n = len(rows)
    lines.append(
        f"| **Missing evidence** | 已解析证据 {n} 行；计算输入 {len(calc.get('inputs', []))} 个 | "
        "计算所需输入缺行 |"
    )
    lines.append(
        "| **No issue found** | — | 以上各项均无异常 |"
    )
    return "\n".join(lines)


def present_case_markdown(sealed: dict, cache: Path) -> str:
    return render_markdown(present_case(sealed, cache))
