"""Graph-assisted retrieval baselines with source-derived candidates only.

Uses the TemporalEvidenceGraph for candidate generation and filtering.
The graph is built from source-derived evidence, not gold labels.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph

from .base import BaseRetriever, CorpusRecord, Question, RetrievalMetadata


class _GraphRetriever(BaseRetriever):
    """KG retrievers only rank candidates supplied by a retrieval-safe graph."""

    def __init__(
        self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None
    ) -> None:
        if not isinstance(graph, TemporalEvidenceGraph):
            raise ValueError("KG retrievers require a TemporalEvidenceGraph retrieval-safe graph")
        super().__init__(corpus, cutoff=cutoff)
        self.graph = graph

    def _candidate_records(self, question: Question) -> list[CorpusRecord]:
        candidate_ids = self._graph_candidate_ids(question)
        return [
            record
            for evidence_id in sorted(candidate_ids)
            if (record := self._corpus_by_evidence_id.get(evidence_id)) is not None
            and self._include(record, question)
        ]

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        raise NotImplementedError


class StaticKGRetriever(_GraphRetriever):
    """Static KG retrieval without temporal filtering."""

    method_name = "static_kg"
    uses_temporal_filter = False
    metadata = RetrievalMetadata(
        method_id="static_kg",
        implementation_mode="production",
        backend="temporal-evidence-graph",
        model_name=None,
        model_revision=None,
        uses_graph=True,
        uses_temporal_filter=False,
        uses_reranker=False,
        uses_verification=False,
        backend_status="production_verified",
    )

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        return self.graph.retrieval_candidate_evidence_ids(question.issuer, question.query)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5


class TemporalKGRetriever(_GraphRetriever):
    """Temporal KG retrieval with valid-time and source-time filtering."""

    method_name = "temporal_kg"
    metadata = RetrievalMetadata(
        method_id="temporal_kg",
        implementation_mode="production",
        backend="temporal-evidence-graph",
        model_name=None,
        model_revision=None,
        uses_graph=True,
        uses_temporal_filter=True,
        uses_reranker=False,
        uses_verification=False,
        backend_status="production_verified",
    )

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        return self.graph.temporal_retrieval_candidate_evidence_ids(
            question.issuer, question.query, question.valid_at, question.effective_source_cutoff
        )

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5
