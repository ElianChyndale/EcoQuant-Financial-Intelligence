"""GRI-QA quant dataset adapter: questions + real environmental tables.

GRI-QA (https://github.com/softlab-unimore/gri_qa, MIT) evaluates table QA over
real corporate sustainability reports. This adapter loads the ``quant`` subset:
266 questions with human-verified numeric answers, cell coordinates (row/col
indices), and the deterministic calculation function each question requires.

Raw data lives in the gitignored ``research/cache/griqa/``; only hashes and
derived metadata are committed.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

FUNCTIONS = {
    "average", "sum", "increase_difference", "reduction_difference",
    "increase_percentage", "reduction_percentage",
}


@dataclass(frozen=True)
class TableQuestion:
    """One GRI-QA question with its gold numeric answer and cell coordinates."""

    question_id: str
    question: str
    value: float
    fn_name: str
    row_indices: tuple[int, ...]
    col_indices: tuple[int, ...]
    company: str
    page: str
    table_nbr: str
    fn_details: str


@dataclass(frozen=True)
class GriqaTable:
    """One real environmental table, parsed into rows and serialized for retrieval."""

    table_id: str
    company: str
    page: str
    table_nbr: str
    rows: tuple[tuple[str, ...], ...]
    text: str


@dataclass(frozen=True)
class GriqaBundle:
    questions: tuple[TableQuestion, ...]
    tables: tuple[GriqaTable, ...]
    manifest: dict[str, object]


def _parse_py_list(value: str) -> list[str]:
    """Parse a CSV field like ``['axa_2023.pdf']`` or ``[33, 33]``."""
    import ast

    parsed = ast.literal_eval(value)
    if not isinstance(parsed, list):
        raise ValueError(f"expected a Python list literal, got: {value!r}")
    return [str(item) for item in parsed]


def _load_questions(quant_path: Path) -> list[TableQuestion]:
    questions: list[TableQuestion] = []
    with quant_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        expected = [
            "pdf name", "checked", "gri", "page nbr", "table nbr", "question",
            "question_type", "question_type_ext", "value", "row indices",
            "col indices", "row/column spanning", "firstk", "fn_details",
        ]
        if header[:14] != expected:
            raise ValueError(f"unexpected GRI-QA quant header: {header[:14]}")
        for index, row in enumerate(reader):
            if len(row) < 14:
                continue
            company_pdf = _parse_py_list(row[0])[0].replace(".pdf", "")
            fn_details = row[13].strip()
            try:
                fn_meta = json.loads(fn_details)
                fn_name = fn_meta["name"]
            except (json.JSONDecodeError, KeyError):
                fn_name = row[7].strip()  # fallback to question_type_ext
            # GRI-QA row/col indices are 1-indexed (verified: subtracting 1 makes
            # the gold calculation exact on real tables). Convert to 0-indexed
            # here so every downstream consumer uses Python indexing directly.
            row_indices = tuple(int(item) - 1 for item in _parse_py_list(row[9]))
            col_indices = tuple(int(item) - 1 for item in _parse_py_list(row[10]))
            questions.append(TableQuestion(
                question_id=f"griqa-quant-{index:04d}",
                question=row[5].strip(),
                value=float(row[8]),
                fn_name=fn_name,
                row_indices=row_indices,
                col_indices=col_indices,
                company=company_pdf,
                page=_parse_py_list(row[3])[0],
                table_nbr=_parse_py_list(row[4])[0],
                fn_details=fn_details,
            ))
    return questions


def _load_table(path: Path) -> GriqaTable:
    """Parse a ``;``-separated environmental table into rows + serialized text.

    Cache layout is flat: ``{company}_{page}_{table}.csv`` where ``company`` may
    itself contain underscores (e.g. ``NASDAQ_DASTY_2023_117_0.csv``). The page
    and table numbers are the final two underscore-separated segments.
    """
    rows: list[tuple[str, ...]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter=";")
        for row in reader:
            rows.append(tuple(cell.strip() for cell in row))
    segments = path.stem.split("_")
    table_nbr = segments[-1]
    page = segments[-2]
    company = "_".join(segments[:-2])
    # Serialize for retrieval: each cell joined, rows separated by newlines.
    text = "\n".join(" | ".join(row) for row in rows)
    return GriqaTable(
        table_id=f"{company}_{page}_{table_nbr}",
        company=company,
        page=page,
        table_nbr=table_nbr,
        rows=tuple(rows),
        text=text,
    )


def load_griqa_quant(cache_dir: Path) -> GriqaBundle:
    """Load the GRI-QA quant questions + tables from the cache directory."""
    quant_path = cache_dir / "gri-qa_quant.csv"
    if not quant_path.exists():
        raise FileNotFoundError(
            f"{quant_path} not found — GRI-QA raw data is cache-only and not committed"
        )
    questions = _load_questions(quant_path)

    tables_dir = cache_dir / "tables"
    tables: list[GriqaTable] = []
    if tables_dir.exists():
        for table_path in sorted(tables_dir.glob("*.csv")):
            tables.append(_load_table(table_path))

    manifest: dict[str, object] = {
        "dataset_id": "griqa-quant-v1",
        "adapter_version": "0.1.0",
        "question_count": len(questions),
        "table_count": len(tables),
        "license": "MIT",
        "redistribution_status": "cache_only",
    }
    return GriqaBundle(
        questions=tuple(questions),
        tables=tuple(tables),
        manifest=manifest,
    )
