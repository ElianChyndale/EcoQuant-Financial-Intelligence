"""FinVEST paper table auto-generation (M9).

Reads experiment result artifacts and generates LaTeX/markdown tables so the
paper tables always match the committed results (never hand-edited).
"""

from __future__ import annotations

import json
from pathlib import Path


def load_result(path: Path) -> dict[str, object]:
    """Load a result JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def result_table_markdown(
    rows: list[dict[str, object]],
    *,
    columns: list[str],
    title: str,
) -> str:
    """Render a markdown table from result rows."""
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [f"**{title}**", "", header, sep]
    for row in rows:
        cells = [str(row.get(col, "")) for col in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def result_table_latex(
    rows: list[dict[str, object]],
    *,
    columns: list[str],
    caption: str,
    label: str,
) -> str:
    """Render a LaTeX table from result rows."""
    col_spec = "l" + "r" * (len(columns) - 1)
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        f"\\begin{{tabular}}{{{col_spec}}}",
        "\\toprule",
        " & ".join(columns) + " \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(str(row.get(col, "")) for col in columns) + " \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}"])
    return "\n".join(lines)


def build_all_tables(results_dir: Path, output_dir: Path) -> list[str]:
    """Generate tables from all committed result artifacts."""
    tables: list[str] = []
    for result_path in sorted(results_dir.glob("e*_summary.json")):
        payload = load_result(result_path)
        experiment = str(payload.get("experiment", result_path.stem))
        # Generic renderer: flatten top-level numeric metrics.
        metrics = payload.get("metrics", payload.get("comparison", {}))
        if isinstance(metrics, dict):
            rows = [{"metric": key, "value": value} for key, value in metrics.items()
                    if isinstance(value, (int, float))]
            tables.append(result_table_markdown(rows, columns=["metric", "value"], title=experiment))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tables.md").write_text("\n\n".join(tables), encoding="utf-8")
    return tables


def artifact_checklist(results_dir: Path) -> list[str]:
    """Return missing-required-artifact violations (A0 gate)."""
    required = [
        "e0_integrity.json", "e1_retrieval_summary.json", "e2_table_summary.json",
        "e3_temporal_summary.json", "e4_verification_summary.json",
        "e5_calibration_summary.json", "e7_commercial_summary.json",
        "e8_integration_summary.json",
    ]
    return [name for name in required if not (results_dir / name).exists()]
