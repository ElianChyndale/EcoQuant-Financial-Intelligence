"""Adapter: frozen EcoQuant corpus (questions.jsonl + source_manifest.csv) -> DatasetBundle.

Gold fields are lifted out of the public query path. The raw questions.jsonl is
the single frozen source; the adapter only projects it into two separated views.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from .schema import DatasetBundle, GoldEvaluationRecord, PublicQueryCase

DATASET_ID = "ecoquant-corpus-v1"
ADAPTER_VERSION = "0.1.0"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _report_period_end(report_period: str) -> date:
    """Report period -> validity end date (four-digit year -> Dec 31)."""
    try:
        return date.fromisoformat(report_period)
    except ValueError:
        pass
    if len(report_period) == 4 and report_period.isdigit():
        return date(int(report_period), 12, 31)
    raise ValueError(f"unsupported report_period: {report_period!r}")


def _load_sources(manifest_path: Path) -> dict[str, dict[str, str]]:
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {row["source_id"]: dict(row) for row in reader}


def _load_questions(questions_path: Path) -> list[Mapping[str, Any]]:
    with questions_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_ecoquant_corpus(
    *, questions_path: Path, manifest_path: Path
) -> DatasetBundle:
    """Load and validate the frozen EcoQuant corpus into a gold-separated bundle."""
    questions = _load_questions(questions_path)
    sources = _load_sources(manifest_path)

    public_cases: list[PublicQueryCase] = []
    gold_records: list[GoldEvaluationRecord] = []
    for row in questions:
        qid = row["question_id"]
        periods = tuple(row["periods"])
        public_cases.append(PublicQueryCase(
            question_id=qid,
            question_type=row["question_type"],
            issuer=row["issuer"],
            query=row["query"],
            periods=periods,
            valid_at=_report_period_end(periods[-1]),
        ))
        gold_records.append(GoldEvaluationRecord(
            question_id=qid,
            question_type=row["question_type"],
            issuer=row["issuer"],
            gold_source_ids=tuple(row["gold_source_ids"]),
            gold_page_ids=tuple(row["gold_page_ids"]),
            gold_block_ids=tuple(row["gold_block_ids"]),
            gold_answer=row["gold_answer"],
            label_provenance=row["label_provenance"],
        ))

    # Validate gold sources exist in the manifest.
    known_sources = set(sources)
    for gold in gold_records:
        unknown = set(gold.gold_source_ids) - known_sources
        if unknown:
            raise ValueError(f"gold_source_ids reference unknown sources: {sorted(unknown)}")

    manifest: dict[str, object] = {
        "dataset_id": DATASET_ID,
        "adapter_version": ADAPTER_VERSION,
        "question_count": len(questions),
        "source_count": len(sources),
        "questions_sha256": _file_sha256(questions_path),
        "manifest_sha256": _file_sha256(manifest_path),
    }
    return DatasetBundle(
        dataset_id=DATASET_ID,
        public_cases=tuple(public_cases),
        gold_records=tuple(gold_records),
        manifest=manifest,
    )
