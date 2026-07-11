"""Graph-assisted retrieval baselines with source-derived candidates only."""

from __future__ import annotations

from .base import BaseRetriever, CorpusRecord, Question, RetrievalMetadata


class _GraphRetriever(BaseRetriever):
    def _candidate_records(self, question: Question) -> list[CorpusRecord]:
        candidate_ids = self._graph_candidate_ids(question)
        candidates = super()._candidate_records(question)
        # A supplied graph is the candidate boundary; ranking never scans it for candidates.
        return [record for record in candidates if record.evidence_id in candidate_ids] if self.graph is not None else candidates

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        raise NotImplementedError


class StaticKGRetriever(_GraphRetriever):
    method_name = "static_kg"
    uses_temporal_filter = False
    metadata = RetrievalMetadata("static_kg", "fixture", "temporal-evidence-graph", None, None, True, False, False, False)

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        candidates = getattr(self.graph, "retrieval_candidate_evidence_ids", None) or getattr(self.graph, "candidate_evidence_ids", None)
        return frozenset(candidates(question.issuer, question.query)) if callable(candidates) else frozenset()

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5


class TemporalKGRetriever(_GraphRetriever):
    method_name = "temporal_kg"
    metadata = RetrievalMetadata("temporal_kg", "fixture", "temporal-evidence-graph", None, None, True, True, False, False)

    def _graph_candidate_ids(self, question: Question) -> frozenset[str]:
        candidates = getattr(self.graph, "temporal_retrieval_candidate_evidence_ids", None)
        if callable(candidates):
            return frozenset(candidates(question.issuer, question.query, question.valid_at, question.effective_source_cutoff))
        candidates = getattr(self.graph, "temporal_candidate_evidence_ids", None)
        return frozenset(candidates(question.issuer, question.query, question.valid_at)) if callable(candidates) else frozenset()

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return super()._score(record, question) + 0.5
