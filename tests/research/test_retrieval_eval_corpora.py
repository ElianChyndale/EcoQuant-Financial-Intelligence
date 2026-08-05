from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.datasets.ecoquant_corpus import load_ecoquant_corpus
from ecoquant.research.datasets.financebench import load_financebench
from ecoquant.research.retrieval_eval.corpora import build_ecoquant_corpus, build_financebench_corpus

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache/financebench"
QUESTIONS = ROOT / "research/questions/questions.jsonl"
MANIFEST = ROOT / "research/sources/source_manifest.csv"


@pytest.fixture(scope="module")
def financebench_bundle():
    return load_financebench(
        questions_path=CACHE / "financebench_open_source.jsonl",
        docs_path=CACHE / "financebench_document_information.jsonl",
    )


@pytest.fixture(scope="module")
def ecoquant_bundle():
    return load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)


def test_financebench_corpus_has_168_evidence_pages(financebench_bundle) -> None:
    corpus, catalog, gold = build_financebench_corpus(financebench_bundle)
    assert len(corpus) == 168
    assert len(catalog) == 168
    assert len(gold.relevant_evidence) == 150
    # every gold evidence_id resolves to a catalog entry
    for relevant in gold.relevant_evidence.values():
        assert relevant <= set(catalog)


def test_financebench_corpus_records_have_evidence_identity(financebench_bundle) -> None:
    corpus, catalog, gold = build_financebench_corpus(financebench_bundle)
    for record in corpus:
        assert record.document_id  # doc_name
        assert record.page_id  # page number
        assert record.text  # full-page text
        assert record.evidence_id in catalog


def test_financebench_gold_page_accuracy_fields(financebench_bundle) -> None:
    corpus, catalog, gold = build_financebench_corpus(financebench_bundle)
    assert len(gold.gold_page_ids) == 150
    for pages in gold.gold_page_ids.values():
        assert pages  # non-empty


def test_ecoquant_corpus_has_unique_records(ecoquant_bundle) -> None:
    corpus, catalog, gold = build_ecoquant_corpus(ecoquant_bundle)
    assert len(corpus) > 0
    # evidence_ids must be unique (retrieval contract + nDCG well-definedness).
    ids = [record.evidence_id for record in corpus]
    assert len(ids) == len(set(ids))
    assert len(gold.relevant_evidence) == 64
    assert all(record.evidence_id in catalog for record in corpus)
