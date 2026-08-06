"""Reference-case sheet generator (Phase 8).

Produces human-readable evidence sheets for candidate reference cases. AI
prepares the CANDIDATE sheets; the researcher approves or rejects each one.
A sheet shows: the question, financial-term definition, exact source accession,
exact concept, original source row/excerpt, unit, real period, filing date,
source cutoff, calculation, minimal evidence, and why ANSWER/REVIEW/ABSTAIN.

These are candidate drafts — never researcher-approved gold until signed off.
"""

from __future__ import annotations

from pathlib import Path

from finvest.benchmark.builders.sec_cases import build_sec_cases


def _term_definition(concept: str) -> str:
    """Short, neutral definition placeholder (researcher owns the finance term)."""
    return f"Definition of {concept} to be confirmed by the researcher."


def build_reference_sheet(case: object, *, ticker: str) -> dict:
    """Build one candidate reference sheet from a builder case."""
    return {
        "case_id": case.case_id,
        "status": "CANDIDATE_UNREVIEWED",
        "question": case.question,
        "term_definition": _term_definition(getattr(case, "metric", None) or "metric"),
        "answer_type": case.answer_type,
        "source_cutoff": str(case.source_cutoff),
        "target_period_start": str(case.target_period_start),
        "target_period_end": str(case.target_period_end),
        "evidence": [
            {
                "evidence_id": ev.evidence_id,
                "concept": ev.concept,
                "unit": ev.unit,
                "period": f"{ev.valid_from} -> {ev.valid_to}",
                "filing_date": str(ev.filing_date),
                "form": ev.document_version,
            }
            for ev in case.evidence_items
        ],
        "calculation": (
            str(case.calculation_program)
            if case.calculation_program is not None else None
        ),
        "decision": case.decision_label,
        "sufficiency": case.sufficiency_label,
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
    # Prefer a spread: positive (derived/extractive) then negative.
    ordered = sorted(built.cases, key=lambda c: (c.answer_type == "unanswerable", c.case_id))
    for case in ordered[:limit]:
        sheet = build_reference_sheet(case, ticker=case.issuer_id)
        (out_dir / f"{case.case_id}.md").write_text(
            _render_markdown(sheet), encoding="utf-8",
        )
        sheets.append(sheet)
    return sheets


def _render_markdown(sheet: dict) -> str:
    lines = [
        f"# Reference Case (CANDIDATE): {sheet['case_id']}",
        "",
        f"**Status:** {sheet['status']}",
        "",
        "## Question",
        sheet["question"],
        "",
        f"**Term definition:** {sheet['term_definition']}",
        "",
        f"**Answer type:** {sheet['answer_type']}",
        f"**Source cutoff:** {sheet['source_cutoff']}",
        f"**Target period:** {sheet['target_period_start']} -> {sheet['target_period_end']}",
        "",
        "## Evidence",
    ]
    for ev in sheet["evidence"]:
        lines.append(
            f"- `{ev['evidence_id']}`: {ev['concept']} · {ev['unit']} · "
            f"{ev['period']} · filed {ev['filing_date']} · {ev['form']}"
        )
    lines += ["", "## Calculation", str(sheet["calculation"] or "—"), "",
              f"**Decision:** {sheet['decision']} · **Sufficiency:** {sheet['sufficiency']}", "",
              "## Researcher review (candidate)",
              "- [ ] I understand the question",
              "- [ ] I found the original source",
              "- [ ] I agree the metric definition",
              "- [ ] I agree the period",
              "- [ ] I agree the unit",
              "- [ ] I can recompute the answer",
              "- [ ] The minimal evidence is sufficient",
              "- [ ] No ambiguity found",
              "",
              "*Candidate sheet prepared by AI. Researcher approval required before use as gold.*",
              ]
    return "\n".join(lines)
