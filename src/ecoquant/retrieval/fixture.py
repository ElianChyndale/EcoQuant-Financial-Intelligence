"""Deterministic fixture retrievers for unit testing.

These retrievers provide reproducible results without requiring model downloads.
They are used only in unit tests and must not be used for final benchmarks.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph

from .base import BaseRetriever, CorpusRecord, Question, RetrievalMetadata, _terms


class FixtureBM25Retriever(BaseRetriever):
    """Deterministic BM25-style lexical baseline for testing."""

    method_name = "bm25"
    metadata = RetrievalMetadata(
        method_id="bm25",
        implementation_mode="fixture",
        backend="deterministic-local",
        model_name="bm25-tokenizer",
        model_revision="local-fixture-20260710",
        uses_graph=False,
        uses_temporal_filter=True,
        uses_reranker=False,
        uses_verification=False,
    )

    def _score(self, record: CorpusRecord, question: Question) -> float:
        query_terms = _terms(question.query)
        document_terms = _terms(record.text)
        if not query_terms:
            return 0.0
        matched = len(query_terms & document_terms)
        return matched / (len(document_terms) + 0.5) + (0.25 if str(record.valid_time.year) in query_terms else 0.0)


class FixtureDenseRetriever(BaseRetriever):
    """Deterministic dense-method proxy for testing."""

    method_name = "dense"
    metadata = RetrievalMetadata(
        method_id="dense",
        implementation_mode="fixture",
        backend="deterministic-local",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_revision="local-fixture-20260710",
        uses_graph=False,
        uses_temporal_filter=True,
        uses_reranker=False,
        uses_verification=False,
    )

    def __init__(self, real_bm25: object | None, corpus: Iterable[CorpusRecord], *, cutoff: date) -> None:
        super().__init__(corpus, cutoff=cutoff)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        query_terms = _terms(question.query)
        document_terms = _terms(record.text)
        union = query_terms | document_terms
        similarity = len(query_terms & document_terms) / len(union) if union else 0.0
        return similarity + (0.25 if str(record.valid_time.year) in query_terms else 0.0)


class _FixtureGraphRetriever(BaseRetriever):
    """Fixture KG retrievers only rank candidates supplied by a retrieval-safe graph."""

    def __init__(
        self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None
    ) -> None:
        if not isinstance(graph, TemporalEvidenceGraph):
            raise ValueError("KG retrievers require a TemporalEvidenceGraph retrieval-safe graph")
        super().__init__(corpus, cutoff=cutoff)
        self.graph = graph

    def _candidate_records(self, question: Question) -> list[CorpusRecord]:
        candidate_ids = self._graph_candidate_ids(question)
        candidates = super()._candidate_records(question)
        return [record for record in candidates if record.evidence_id in candidate_ids]

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        raise NotImplementedError


class FixtureStaticKGRetriever(_FixtureGraphRetriever):
    method_name = "static_kg"
    uses_temporal_filter = False
    metadata = RetrievalMetadata(
        method_id="static_kg",
        implementation_mode="fixture",
        backend="temporal-evidence-graph",
        model_name=None,
        model_revision=None,
        uses_graph=True,
        uses_temporal_filter=False,
        uses_reranker=False,
        uses_verification=False,
    )

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        return self.graph.retrieval_candidate_evidence_ids(question.issuer, question.query)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5


class FixtureTemporalKGRetriever(_FixtureGraphRetriever):
    method_name = "temporal_kg"
    metadata = RetrievalMetadata(
        method_id="temporal_kg",
        implementation_mode="fixture",
        backend="temporal-evidence-graph",
        model_name=None,
        model_revision=None,
        uses_graph=True,
        uses_temporal_filter=True,
        uses_reranker=False,
        uses_verification=False,
    )

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        return self.graph.temporal_retrieval_candidate_evidence_ids(
            question.issuer, question.query, question.valid_at, question.effective_source_cutoff
        )

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5


def _period_reranker(record: CorpusRecord, question: Question, score: float) -> float:
    return score + (0.5 if str(record.valid_time.year) in question.query else 0.0)


class FixtureTemporalKGRerankRetriever(FixtureTemporalKGRetriever):
    method_name = "temporal_kg_rerank"
    metadata = RetrievalMetadata(
        method_id="temporal_kg_rerank",
        implementation_mode="fixture",
        backend="temporal-evidence-graph",
        model_name="BAAI/bge-reranker-base",
        model_revision="local-fixture-20260710",
        uses_graph=True,
        uses_temporal_filter=True,
        uses_reranker=True,
        uses_verification=False,
    )

    def __init__(
        self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None
    ) -> None:
        super().__init__(corpus, cutoff=cutoff, graph=graph)
        self.reranker = _period_reranker

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return self.reranker(record, question, super()._score(record, question))


def _source_verifier(record: CorpusRecord, question: Question) -> str:
    if record.valid_time > question.valid_at:
        return "invalid_for_requested_time"
    if record.source_time is not None and record.source_time > question.effective_source_cutoff:
        return "published_after_source_cutoff"
    return "time_verified"


class FixtureTemporalKGVerifyRetriever(FixtureTemporalKGRerankRetriever):
    method_name = "temporal_kg_verify"
    metadata = RetrievalMetadata(
        method_id="temporal_kg_verify",
        implementation_mode="fixture",
        backend="temporal-evidence-graph",
        model_name="source-time-verifier",
        model_revision="local-fixture-20260710",
        uses_graph=True,
        uses_temporal_filter=True,
        uses_reranker=True,
        uses_verification=True,
    )

    def __init__(
        self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None
    ) -> None:
        super().__init__(corpus, cutoff=cutoff, graph=graph)
        self.verifier = _source_verifier

    def _verification_status(self, record: CorpusRecord, question: Question) -> str:
        return self.verifier(record, question)
