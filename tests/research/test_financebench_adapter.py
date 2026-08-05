from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.datasets.financebench import load_financebench
from ecoquant.research.datasets.schema import DatasetBundle, GoldEvaluationRecord, PublicQueryCase

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/financebench"


@pytest.fixture(scope="module")
def bundle() -> DatasetBundle:
    return load_financebench(
        questions_path=CACHE / "financebench_open_source.jsonl",
        docs_path=CACHE / "financebench_document_information.jsonl",
    )


def test_financebench_bundle_counts(bundle) -> None:
    assert isinstance(bundle, DatasetBundle)
    assert len(bundle.public_cases) == 150
    assert len(bundle.gold_records) == 150
    assert bundle.manifest["dataset_id"] == "financebench-sample-v1"
    assert bundle.manifest["question_count"] == 150


def test_public_case_carries_no_gold(bundle) -> None:
    for case in bundle.public_cases:
        assert isinstance(case, PublicQueryCase)
        assert case.question_id
        assert case.issuer  # company as issuer
        assert case.query
        assert "gold" not in case.__dict__


def test_gold_record_has_evidence_fields(bundle) -> None:
    for gold in bundle.gold_records:
        assert isinstance(gold, GoldEvaluationRecord)
        assert gold.question_id
        assert gold.gold_answer
        assert gold.gold_source_ids  # doc_name(s)
        assert gold.gold_page_ids  # page number(s)
        assert gold.gold_block_ids  # evidence text (as block)


def test_public_and_gold_align_one_to_one(bundle) -> None:
    assert {c.question_id for c in bundle.public_cases} == {g.question_id for g in bundle.gold_records}
    assert len(bundle.public_cases) == 150


def test_manifest_records_page_convention_and_license(bundle) -> None:
    assert bundle.manifest["page_convention"] == "zero_indexed_int"
    assert bundle.manifest["license_status"] == "unconfirmed"
    assert bundle.manifest["redistribution_status"] == "cache_only"


def test_company_split_has_no_cross_split_leakage(bundle) -> None:
    """E0 gate for FinanceBench: split by company; no company spans dev/test."""
    companies = {case.issuer for case in bundle.public_cases}
    companies_sorted = sorted(companies)
    dev_companies = set(companies_sorted[::2])
    test_companies = set(companies_sorted[1::2])
    dev_questions = {case.question_id for case in bundle.public_cases if case.issuer in dev_companies}
    test_questions = {case.question_id for case in bundle.public_cases if case.issuer in test_companies}
    assert dev_questions.isdisjoint(test_questions)
    assert len(dev_questions) + len(test_questions) == 150
