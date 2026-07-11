from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from scripts.fetch_public_reports import fetch_report

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "research/sources/source_manifest.csv"
QUESTIONS_PATH = ROOT / "research/questions/questions.jsonl"
QUALITATIVE_LABELS_PATH = ROOT / "research/labels/qualitative_labels.jsonl"
AUDIT_LABELS_PATH = ROOT / "research/labels/audit_labels.jsonl"

MANIFEST_COLUMNS = [
    "source_id",
    "issuer",
    "title",
    "report_period",
    "official_url",
    "access_date",
    "sha256",
    "media_type",
    "redistribution_status",
    "cache_policy",
]
QUESTION_TYPES = {
    "evidence_lookup": 16,
    "numeric_change": 16,
    "contradiction_or_supersession": 16,
    "table_citation": 16,
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
QUERY_PLACEHOLDER = re.compile(r"\b(?:undefined|todo|tbd|placeholder)\b", re.IGNORECASE)


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MANIFEST_COLUMNS
        return list(reader)


def load_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_frozen_corpus_contract() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    questions = load_jsonl(QUESTIONS_PATH)

    assert len(manifest) == 12
    assert len({(row["issuer"], row["report_period"]) for row in manifest}) == 12
    assert len(questions) == 64
    assert Counter(q["question_type"] for q in questions) == QUESTION_TYPES

    source_ids = {row["source_id"] for row in manifest}
    assert all(row["official_url"].startswith("https://") for row in manifest)
    assert all(SHA256.fullmatch(row["sha256"]) for row in manifest)
    assert all(row["media_type"] == "application/pdf" for row in manifest)
    assert all(row["redistribution_status"] == "not_confirmed_non_redistributable" for row in manifest)
    assert all("untracked" in row["cache_policy"] for row in manifest)

    required_question_fields = {
        "question_id",
        "question_type",
        "query",
        "issuer",
        "periods",
        "gold_source_ids",
        "gold_page_ids",
        "gold_block_ids",
        "gold_answer",
        "label_provenance",
    }
    assert all(required_question_fields <= q.keys() for q in questions)
    assert all(set(q["gold_source_ids"]) <= source_ids for q in questions)
    assert all(q["gold_page_ids"] and q["gold_block_ids"] for q in questions)
    assert all(q["label_provenance"] == "manual_source_review" for q in questions)
    assert all(isinstance(q["query"], str) and q["query"].strip() for q in questions)
    assert all(not QUERY_PLACEHOLDER.search(q["query"]) for q in questions)


def test_frozen_label_contract() -> None:
    qualitative_labels = load_jsonl(QUALITATIVE_LABELS_PATH)
    audit_labels = load_jsonl(AUDIT_LABELS_PATH)

    assert len(qualitative_labels) == 16
    assert len(audit_labels) == 16
    assert all(label["label_provenance"] == "manual_source_review" for label in qualitative_labels)
    assert all(label["label_provenance"] == "derived_and_audited" for label in audit_labels)


def test_question_semantics_are_grounded_in_numeric_tables_and_temporal_comparisons() -> None:
    questions = load_jsonl(QUESTIONS_PATH)
    by_id = {question["question_id"]: question for question in questions}

    numeric_questions = [question for question in questions if question["question_type"] == "numeric_change"]
    assert all(question["metric"] and question["unit"] for question in numeric_questions)
    assert all(len(question["reported_values"]) == 2 for question in numeric_questions)
    assert all(
        question["reported_values"][1] - question["reported_values"][0] == pytest.approx(question["derived_change"])
        for question in numeric_questions
    )

    table_questions = [question for question in questions if question["question_type"] == "table_citation"]
    assert all(question["table_title"] and question["table_row"] for question in table_questions)
    assert all(isinstance(question["reported_value"], (int, float)) for question in table_questions)

    temporal_questions = [question for question in questions if question["question_type"] == "contradiction_or_supersession"]
    assert all(len(question["gold_source_ids"]) == 2 for question in temporal_questions)
    assert all(len(question["periods"]) == 2 for question in temporal_questions)
    assert all(question["temporal_reasoning"] for question in temporal_questions)
    assert all("cover" not in question["gold_answer"].lower() for question in temporal_questions)

    qualitative_labels = load_jsonl(QUALITATIVE_LABELS_PATH)
    assert {label["question_id"] for label in qualitative_labels} == {question["question_id"] for question in temporal_questions}
    assert all(by_id[label["question_id"]]["gold_source_ids"] == label["evidence_source_ids"] for label in qualitative_labels)
    assert all(by_id[label["question_id"]]["gold_page_ids"] == label["evidence_page_ids"] for label in qualitative_labels)

    audit_labels = load_jsonl(AUDIT_LABELS_PATH)
    assert all(label["source_question_id"] in by_id for label in audit_labels)
    assert all(by_id[label["source_question_id"]]["question_type"] in {"numeric_change", "table_citation"} for label in audit_labels)
    assert all(isinstance(label["label_type"], str) and label["label_type"].strip() for label in audit_labels)
    assert all(isinstance(label["metric"], str) and label["metric"].strip() for label in audit_labels)
    assert all(isinstance(label["unit"], str) and label["unit"].strip() for label in audit_labels)
    assert all(isinstance(label["derivation_formula"], str) and label["derivation_formula"].strip() for label in audit_labels)
    assert all(label["metric"] == by_id[label["source_question_id"]]["metric"] for label in audit_labels)
    assert all(label["unit"] == by_id[label["source_question_id"]]["unit"] for label in audit_labels)
    assert all(isinstance(label["derived_value"], (int, float)) for label in audit_labels)
    assert all(label["audit_provenance"] == "derived_from_frozen_question_and_manually_audited_against_pdf_table" for label in audit_labels)


def test_fetcher_refuses_escaping_source_id_before_writing(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    row = {
        "source_id": "../escape",
        "official_url": "https://www.aib.ie/not-fetched.pdf",
        "sha256": "0" * 64,
    }

    with pytest.raises(ValueError, match="unsafe source_id"):
        fetch_report(row, cache_dir)

    assert not (tmp_path / "escape.pdf").exists()
