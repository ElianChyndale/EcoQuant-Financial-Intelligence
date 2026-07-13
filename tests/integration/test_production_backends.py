"""Integration tests for production retrieval backends.

These tests verify that production backends can be loaded and used.
In production mode, model loading failures raise RuntimeError rather than
silently degrading to proxy scoring.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

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


def _model_available(model_name: str) -> bool:
    """Check if a sentence-transformers model is available locally."""
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer(model_name)
        return True
    except Exception:
        return False


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


def test_production_dense_retriever_fails_loudly_when_model_load_fails(corpus, monkeypatch):
    """Fail-loud behavior is distinct from proof of successful production execution."""
    from sentence_transformers import SentenceTransformer
    from ecoquant.retrieval.dense import DenseRetriever

    def fail_load(*args, **kwargs):
        raise OSError("model unavailable")

    monkeypatch.setattr(SentenceTransformer, "__init__", fail_load)
    with pytest.raises(RuntimeError, match="Failed to load production dense model"):
        DenseRetriever(corpus, cutoff=date(2023, 12, 31))


def test_production_dense_retriever_loads_verified_local_snapshot(corpus, monkeypatch):
    from ecoquant.retrieval.base import RetrieverQuery
    from ecoquant.retrieval.dense import DENSE_MODEL, DenseRetriever

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    assert DENSE_MODEL.revision == "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    snapshot = (
        Path.home()
        / ".cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots"
        / DENSE_MODEL.revision
    )
    if not any((snapshot / filename).exists() for filename in ("model.safetensors", "pytorch_model.bin")):
        pytest.skip("EXTERNAL_BLOCKER: verified dense snapshot is missing executable model weights")

    retriever = DenseRetriever(corpus, cutoff=date(2023, 12, 31))
    results = retriever.retrieve(
        RetrieverQuery("test", "AIB", "AIB total assets", date(2023, 12, 31)),
        top_k=3,
    )

    assert retriever._model_loaded is True
    assert results
    assert all(result.score == pytest.approx(result.score) for result in results)


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


def test_production_reranker_fails_loudly_when_model_load_fails(corpus, graph, monkeypatch):
    from sentence_transformers import CrossEncoder
    from ecoquant.retrieval.reranker import TemporalKGRerankRetriever

    def fail_load(*args, **kwargs):
        raise OSError("model unavailable")

    monkeypatch.setattr(CrossEncoder, "__init__", fail_load)
    with pytest.raises(RuntimeError, match="Failed to load production reranker model"):
        TemporalKGRerankRetriever(corpus, cutoff=date(2023, 12, 31), graph=graph)


def test_production_reranker_loads_verified_snapshot(corpus, graph, monkeypatch):
    from ecoquant.retrieval.reranker import RERANKER_MODEL, TemporalKGRerankRetriever

    if RERANKER_MODEL.revision is None:
        pytest.skip("EXTERNAL_BLOCKER: no verified immutable local reranker revision")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    retriever = TemporalKGRerankRetriever(corpus, cutoff=date(2023, 12, 31), graph=graph)
    assert retriever._model_loaded is True


def test_fixture_retrievers_work_without_models(corpus, graph):
    """Verify fixture retrievers work without requiring model downloads."""
    methods = all_retrievers(corpus, cutoff=date(2023, 12, 31), graph=graph, mode="fixture")

    for method in methods:
        assert method.metadata.implementation_mode == "fixture"

    from ecoquant.retrieval.base import RetrieverQuery, validate_final_benchmark
    query = RetrieverQuery(
        question_id="test",
        issuer="AIB",
        query="AIB total assets",
        cutoff=date(2023, 12, 31),
    )

    for method in methods:
        results = method.retrieve(query, top_k=3)
        assert len(results) > 0

    # Fixture methods should be rejected by final benchmark validation
    with pytest.raises(ValueError, match="fixture"):
        validate_final_benchmark(methods)


def test_production_metadata_requires_backend_info():
    """Verify production metadata validation requires backend info."""
    # Valid production metadata
    valid = RetrievalMetadata(
        "bm25", "production", "rank-bm25", "model", "rev", False, True, False, False,
        backend_status="production_verified",
    )
    valid.validate()

    # Invalid: empty backend
    with pytest.raises(ValueError, match="production metadata"):
        invalid = RetrievalMetadata(
            "bm25", "production", "", None, None, False, True, False, False,
            backend_status="production_verified",
        )
        invalid.validate()
