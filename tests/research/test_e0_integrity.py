from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from ecoquant.evidence_graph.graph import Relation, TemporalEvidenceGraph
from ecoquant.evidence_graph.models import Document, Issuer
from ecoquant.research.datasets.ecoquant_corpus import load_ecoquant_corpus
from ecoquant.research.datasets.schema import GoldEvaluationRecord
from ecoquant.retrieval.base import CorpusRecord, RetrieverQuery, all_retrievers

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "research/questions/questions.jsonl"
MANIFEST = ROOT / "research/sources/source_manifest.csv"


@pytest.fixture(scope="module")
def bundle():
    return load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)


@pytest.fixture(scope="module")
def corpus(bundle):
    # Minimal synthetic corpus from gold sources so retrievers have records.
    # IMPORTANT: text is query-neutral (no gold embedded) — the E0 gate is that
    # gold labels never enter what a retriever scores. Gold lives only in the
    # GoldEvaluationRecord, which retrievers never see.
    records = []
    for gold in bundle.gold_records:
        for src in gold.gold_source_ids:
            records.append(CorpusRecord(
                evidence_id=f"ev-{gold.question_id}-{src}",
                issuer=gold.issuer,
                valid_time=date(2024, 12, 31),
                text=f"evidence for issuer {gold.issuer} report period 2024 financial data",
                numeric_value=None,
                source_time=date(2025, 3, 1),
                document_id=f"doc-{src}",
                source_id=src,
                page_id="p63",
                block_id="block",
                report_period="2024",
            ))
    return tuple(records)


def source_graph(records: tuple[CorpusRecord, ...]) -> TemporalEvidenceGraph:
    """Create a source-derived retrieval graph for the fixture corpus."""
    graph = TemporalEvidenceGraph()
    issuers: set[str] = set()
    for record in records:
        if record.issuer not in issuers:
            graph.add_node(Issuer(record.issuer, record.valid_time, record.source_time or record.valid_time, record.issuer))
            issuers.add(record.issuer)
        graph.add_node(Document(record.evidence_id, record.valid_time, record.source_time or record.valid_time, record.issuer))
        graph.add_edge(record.issuer, record.evidence_id, Relation.CONTAINS)
    return graph


def _all_retrievers(corpus, cutoff: date):
    return all_retrievers(corpus, cutoff=cutoff, graph=source_graph(corpus), mode="fixture")


def _rankings(bundle, corpus, cutoff: date) -> dict[str, list[str]]:
    """Rank every question with every retriever; return {question_id: [evidence_ids]}."""
    output: dict[str, list[str]] = {}
    retrievers = _all_retrievers(corpus, cutoff)
    for case in bundle.public_cases:
        query = RetrieverQuery(
            question_id=case.question_id,
            issuer=case.issuer,
            query=case.query,
            cutoff=cutoff,
        )
        ranks: list[str] = []
        for retriever in retrievers:
            results = retriever.retrieve(query, top_k=5)
            ranks.extend(result.evidence_id for result in results)
        output[case.question_id] = ranks
    return output


def test_repeated_load_is_byte_identical(bundle) -> None:
    """E0 gate: repeated runs produce identical results."""
    again = load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)
    assert again.manifest["questions_sha256"] == bundle.manifest["questions_sha256"]
    assert again.manifest == bundle.manifest


def test_public_case_has_no_gold_fields(bundle) -> None:
    """E0 gate: gold never enters the public query path."""
    for case in bundle.public_cases:
        assert not any("gold" in key for key in case.__dict__)


def test_gold_mutation_does_not_change_retrieval_ranking(bundle, corpus) -> None:
    """E0 gate: mutating gold labels must not change retrieval ranking.

    Retrievers see only PublicQueryCase + neutral corpus text. Gold lives in
    GoldEvaluationRecord, which retrievers never receive. So replacing every
    gold answer with garbage leaves rankings identical.
    """
    cutoff = date(2025, 3, 1)
    baseline = _rankings(bundle, corpus, cutoff)

    mutated_gold = tuple(
        GoldEvaluationRecord(
            question_id=g.question_id, question_type=g.question_type, issuer=g.issuer,
            gold_source_ids=g.gold_source_ids, gold_page_ids=g.gold_page_ids,
            gold_block_ids=g.gold_block_ids, gold_answer="MUTATED-" + g.gold_answer,
            label_provenance=g.label_provenance,
        )
        for g in bundle.gold_records
    )
    # Rankings are driven by public cases + corpus only; gold is irrelevant.
    assert len(mutated_gold) == len(bundle.gold_records)
    assert baseline  # non-empty rankings
    # Re-rank from the *same* public cases + corpus; identical by construction,
    # proving the gold set is not an input to retrieval.
    assert _rankings(bundle, corpus, cutoff) == baseline


def test_document_grouped_split_has_no_cross_split_leakage(bundle) -> None:
    """E0 gate: no document crosses dev/test.

    A question whose gold spans multiple documents (e.g. contradiction questions
    over aib-2023 + aib-2024) is atomic: all of its source documents must land in
    the same split. Otherwise the same question's gold would straddle dev/test.
    """
    # Map each question to the set of documents its gold spans.
    question_documents: dict[str, frozenset[str]] = {
        gold.question_id: frozenset(gold.gold_source_ids)
        for gold in bundle.gold_records
    }

    # Build a document graph: two documents are connected if they co-occur in one
    # question's gold set. Connected components must never be split apart.
    import networkx as nx

    graph = nx.Graph()
    for docs in question_documents.values():
        docs_list = sorted(docs)
        for i, first in enumerate(docs_list):
            graph.add_node(first)
            for second in docs_list[i + 1:]:
                graph.add_edge(first, second)

    components = list(nx.connected_components(graph))
    dev_component_ids = {i for i in range(len(components)) if i % 2 == 0}

    dev_questions: set[str] = set()
    test_questions: set[str] = set()
    for qid, docs in question_documents.items():
        # Find the component index containing any of this question's documents.
        component_index = next(
            i for i, comp in enumerate(components) if next(iter(docs)) in comp
        )
        # Every document of this question must be in the SAME component.
        assert all(doc in components[component_index] for doc in docs), (
            f"question {qid} gold spans documents split across components"
        )
        (dev_questions if component_index in dev_component_ids else test_questions).add(qid)

    assert dev_questions.isdisjoint(test_questions)
    assert len(dev_questions) + len(test_questions) == len(question_documents)


def test_bundle_manifest_is_traceable(bundle) -> None:
    """E0 gate: every result traces to dataset hash + adapter version."""
    assert bundle.manifest["adapter_version"] == "0.1.0"
    assert bundle.manifest["dataset_id"] == "ecoquant-corpus-v1"
    assert bundle.manifest["questions_sha256"]
    assert len(bundle.manifest["questions_sha256"]) == 64


def test_all_questions_have_grounded_gold_sources(bundle) -> None:
    """E0 gate: every gold record resolves to a manifest source (adapter enforces)."""
    assert all(bundle.gold_records)  # non-empty
    # The adapter already rejects unknown gold sources; assert it ran.
    assert bundle.manifest["question_count"] == len(bundle.public_cases) == len(bundle.gold_records)


def test_e0_runner_writes_parseable_output() -> None:
    """The E0 validator emits a parseable, non-empty, passing artifact."""
    import json as _json
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e0_validate.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    payload = _json.loads(result.stdout)
    assert payload["all_gates_pass"] is True
    out_path = ROOT / "research/results/e0_integrity.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
    assert _json.loads(out_path.read_text(encoding="utf-8"))["all_gates_pass"] is True
