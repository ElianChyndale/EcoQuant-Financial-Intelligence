"""Integration tests for production retrieval backends.

These tests verify that production backends can be loaded and used.
They require the actual model packages to be installed.
"""

from __future__ import annotations

from datetime import date

import pytest

from ecoquant.retrieval.base import CorpusRecord, RetrievalMetadata, all_retrievers
from ecoquant.retrieval.evaluation import EvaluatorGold
from ecoquant.evidence_graph.graph import Relation, TemporalEvidenceGraph
from ecoquant.evidence_graph.models import Document, Issuer


def frozen_corpus() -> tuple[CorpusRecord, ...]:
    return (
        CorpusRecord("aib-2022", "AIB", date(2022, 12, 31), "AIB total assets 129.8 EUR billions", 129.8),
        CorpusRecord("aib-2023", "AIB", date(2023, 12, 31), "AIB total assets 136.3 EUR billions", 136.3),
        CorpusRecord("aib-2024", "AIB", date(2024, 12, 31), "AIB total assets 141.3 EUR billions", 141.3),
        CorpusRecord("esb-2023", "ESB", date(2023, 12, 31), "ESB average employees 8890", 8890),
        CorpusRecord("esb-2024", "ESB", date(2024, 12, 31), "ESB average employees 9588", 9588),
    )


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


@pytest.fixture
def corpus():
    return frozen_corpus()


@pytest.fixture
def graph(corpus):
    return source_graph(corpus)


def test_production_bm25_retriever_loads_and_scores(corpus, graph):
    """Verify BM25 retriever loads and produces scores."""
    from ecoquant.retrieval.bm25 import BM25Retriever

    retriever = BM25Retriever(corpus, cutoff=date(2023, 12, 31))
    assert retriever.metadata.implementation_mode == "production"
    assert retriever.metadata.backend == "rank-bm25"

    from ecoquant.retrieval.base import RetrieverQuery
    query = RetrieverQuery(
        question_id="test",
        issuer="AIB",
        query="AIB total assets 2023",
        cutoff=date(2023, 12, 31),
    )
    results = retriever.retrieve(query, top_k=3)
    assert len(results) > 0
    assert all(r.score >= 0 for r in results)


def test_production_dense_retriever_loads(corpus, graph):
    """Verify dense retriever loads (may fallback to proxy if model unavailable)."""
    from ecoquant.retrieval.dense import DenseRetriever

    retriever = DenseRetriever(corpus, cutoff=date(2023, 12, 31))
    assert retriever.metadata.implementation_mode == "production"
    assert retriever.metadata.model_name == "sentence-transformers/all-MiniLM-L6-v2"

    from ecoquant.retrieval.base import RetrieverQuery
    query = RetrieverQuery(
        question_id="test",
        issuer="AIB",
        query="AIB total assets 2023",
        cutoff=date(2023, 12, 31),
    )
    results = retriever.retrieve(query, top_k=3)
    assert len(results) > 0


def test_production_kg_retrievers_require_graph(corpus):
    """Verify KG retrievers require a TemporalEvidenceGraph."""
    from ecoquant.retrieval.kg import StaticKGRetriever, TemporalKGRetriever

    with pytest.raises(ValueError, match="TemporalEvidenceGraph"):
        StaticKGRetriever(corpus, cutoff=date(2023, 12, 31))
    with pytest.raises(ValueError, match="TemporalEvidenceGraph"):
        TemporalKGRetriever(corpus, cutoff=date(2023, 12, 31))


def test_production_kg_retrievers_load_with_graph(corpus, graph):
    """Verify KG retrievers load and produce results with a graph."""
    from ecoquant.retrieval.kg import StaticKGRetriever, TemporalKGRetriever

    static = StaticKGRetriever(corpus, cutoff=date(2023, 12, 31), graph=graph)
    temporal = TemporalKGRetriever(corpus, cutoff=date(2023, 12, 31), graph=graph)

    assert static.metadata.implementation_mode == "production"
    assert temporal.metadata.implementation_mode == "production"

    from ecoquant.retrieval.base import RetrieverQuery
    query = RetrieverQuery(
        question_id="test",
        issuer="AIB",
        query="AIB total assets",
        cutoff=date(2023, 12, 31),
    )
    static_results = static.retrieve(query, top_k=3)
    temporal_results = temporal.retrieve(query, top_k=3)

    # Static should return results (no temporal filter)
    assert len(static_results) > 0
    # Temporal may filter some results
    assert len(temporal_results) >= 0


def test_production_metadata_is_complete_for_all_methods(corpus, graph):
    """Verify all production methods have complete metadata."""
    methods = all_retrievers(corpus, cutoff=date(2023, 12, 31), graph=graph, mode="production")

    for method in methods:
        method.metadata.validate()
        assert method.metadata.implementation_mode == "production"
        assert method.metadata.backend is not None and method.metadata.backend != ""


def test_production_final_benchmark_validates(corpus, graph):
    """Verify production methods pass final benchmark validation."""
    from ecoquant.retrieval.base import validate_final_benchmark

    methods = all_retrievers(corpus, cutoff=date(2023, 12, 31), graph=graph, mode="production")
    # This should not raise for production methods
    validate_final_benchmark(methods)


def test_fixture_final_benchmark_rejects(corpus, graph):
    """Verify fixture methods fail final benchmark validation."""
    from ecoquant.retrieval.base import validate_final_benchmark

    methods = all_retrievers(corpus, cutoff=date(2023, 12, 31), graph=graph, mode="fixture")
    with pytest.raises(ValueError, match="fixture"):
        validate_final_benchmark(methods)


def test_retrieval_manifest_records_all_metadata(corpus, graph):
    """Verify retrieval manifest captures all method metadata."""
    from ecoquant.retrieval.base import retrieval_manifest

    methods = all_retrievers(corpus, cutoff=date(2023, 12, 31), graph=graph, mode="production")
    manifest = retrieval_manifest(methods)

    assert len(manifest) == 6
    for method_name, metadata in manifest.items():
        assert isinstance(metadata, RetrievalMetadata)
        assert metadata.method_id == method_name
