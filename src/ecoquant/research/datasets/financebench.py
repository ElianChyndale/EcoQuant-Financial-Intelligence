"""Adapter: FinanceBench public sample -> DatasetBundle (company-grouped, gold-separated).

FinanceBench (https://github.com/patronus-ai/financebench) is a real financial QA
benchmark over 10-K/10-Q/8-K/earnings reports. The public sample has 150 questions,
32 companies, and 84 documents, each question carrying human-annotated answer and
page-level evidence. The raw JSONL lives in the gitignored `research/cache/`; only
hashes and derived metadata are committed. The repository declares no explicit
license, so this dataset is `cache_only` and never redistributed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from .schema import DatasetBundle, GoldEvaluationRecord, PublicQueryCase

DATASET_ID = "financebench-sample-v1"
ADAPTER_VERSION = "0.1.0"
PAGE_CONVENTION = "zero_indexed_int"
LICENSE_STATUS = "unconfirmed"
REDISTRIBUTION_STATUS = "cache_only"

# FinanceBench has no temporal semantics; a neutral future cutoff keeps the
# PublicQueryCase contract (a required valid_at date) satisfied without inventing
# temporal meaning that the dataset does not carry.
NEUTRAL_VALID_AT = date(2026, 1, 1)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> list[Mapping[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_financebench(
    *, questions_path: Path, docs_path: Path
) -> DatasetBundle:
    """Load the FinanceBench public sample into a gold-separated, company-grouped bundle."""
    questions = _load_jsonl(questions_path)
    docs = _load_jsonl(docs_path)
    doc_by_name = {doc["doc_name"]: doc for doc in docs}

    public_cases: list[PublicQueryCase] = []
    gold_records: list[GoldEvaluationRecord] = []
    for row in questions:
        qid = row["financebench_id"]
        evidence = row["evidence"]
        doc_names = tuple(doc["doc_name"] for doc in evidence)
        page_nums = tuple(str(doc["evidence_page_num"]) for doc in evidence)
        block_ids = tuple(doc["evidence_text"][:120] for doc in evidence)
        public_cases.append(PublicQueryCase(
            question_id=qid,
            question_type=row["question_type"],
            issuer=row["company"],
            query=row["question"],
            periods=(row["doc_name"],),
            valid_at=NEUTRAL_VALID_AT,
        ))
        gold_records.append(GoldEvaluationRecord(
            question_id=qid,
            question_type=row["question_type"],
            issuer=row["company"],
            gold_source_ids=doc_names,
            gold_page_ids=page_nums,
            gold_block_ids=block_ids,
            gold_answer=row["answer"],
            label_provenance="human_annotated",
        ))

    # Validate doc_names resolve to document metadata.
    for gold in gold_records:
        unknown = [doc for doc in gold.gold_source_ids if doc not in doc_by_name]
        if unknown:
            raise ValueError(f"gold_source_ids reference unknown documents: {sorted(set(unknown))}")

    manifest: dict[str, object] = {
        "dataset_id": DATASET_ID,
        "adapter_version": ADAPTER_VERSION,
        "question_count": len(questions),
        "company_count": len({row["company"] for row in questions}),
        "document_count": len(doc_by_name),
        "page_convention": PAGE_CONVENTION,
        "license_status": LICENSE_STATUS,
        "redistribution_status": REDISTRIBUTION_STATUS,
        "questions_sha256": _file_sha256(questions_path),
        "docs_sha256": _file_sha256(docs_path),
    }
    return DatasetBundle(
        dataset_id=DATASET_ID,
        public_cases=tuple(public_cases),
        gold_records=tuple(gold_records),
        manifest=manifest,
    )
