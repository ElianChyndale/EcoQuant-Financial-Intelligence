from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ecoquant.research.datasets.ecoquant_corpus import load_ecoquant_corpus
from ecoquant.research.datasets.schema import DatasetBundle, GoldEvaluationRecord, PublicQueryCase

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "research/questions/questions.jsonl"
MANIFEST = ROOT / "research/sources/source_manifest.csv"


def test_bundle_counts_and_schema() -> None:
    bundle = load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)
    assert isinstance(bundle, DatasetBundle)
    assert len(bundle.public_cases) == 64
    assert len(bundle.gold_records) == 64
    assert bundle.manifest["dataset_id"] == "ecoquant-corpus-v1"
    assert bundle.manifest["question_count"] == 64
    assert bundle.manifest["source_count"] == 12


def test_public_case_carries_no_gold() -> None:
    bundle = load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)
    for case in bundle.public_cases:
        assert isinstance(case, PublicQueryCase)
        assert case.question_id
        assert case.issuer
        assert case.query
        assert case.periods
        assert isinstance(case.valid_at, date)
        assert "gold" not in case.__dict__


def test_gold_record_carries_expected_fields() -> None:
    bundle = load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)
    for gold in bundle.gold_records:
        assert isinstance(gold, GoldEvaluationRecord)
        assert gold.question_id
        assert gold.gold_source_ids
        assert gold.gold_page_ids
        assert gold.gold_block_ids
        assert gold.gold_answer


def test_public_and_gold_align_one_to_one() -> None:
    bundle = load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)
    public_ids = {case.question_id for case in bundle.public_cases}
    gold_ids = {gold.question_id for gold in bundle.gold_records}
    assert public_ids == gold_ids
    assert len(public_ids) == 64
