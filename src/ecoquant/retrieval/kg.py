"""Graph-assisted retrieval baselines with source-derived candidates only."""

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
        candidates = super()._candidate_records(question)
        return [record for record in candidates if record.evidence_id in candidate_ids]

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        raise NotImplementedError


class StaticKGRetriever(_GraphRetriever):
    method_name = "static_kg"
    uses_temporal_filter = False
    metadata = RetrievalMetadata("static_kg", "fixture", "temporal-evidence-graph", None, None, True, False, False, False)

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        return self.graph.retrieval_candidate_evidence_ids(question.issuer, question.query)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5


class TemporalKGRetriever(_GraphRetriever):
    method_name = "temporal_kg"
    metadata = RetrievalMetadata("temporal_kg", "fixture", "temporal-evidence-graph", None, None, True, True, False, False)

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        return self.graph.temporal_retrieval_candidate_evidence_ids(
            question.issuer, question.query, question.valid_at, question.effective_source_cutoff
        )

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5
