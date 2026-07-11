"""Static and cutoff-aware graph retrieval baselines."""

from __future__ import annotations

from .base import BaseRetriever, CorpusRecord, Question


class StaticKGRetriever(BaseRetriever):
    method_name = "static_kg"
    uses_temporal_filter = False

    def _score(self, record: CorpusRecord, question: Question) -> float:
        graph_bonus = 0.25 if record.evidence_id in self.graph_evidence_ids(question) else 0.0
        return super()._score(record, question) + 0.5 + graph_bonus


class TemporalKGRetriever(BaseRetriever):
    method_name = "temporal_kg"

    def _score(self, record: CorpusRecord, question: Question) -> float:
        graph_bonus = 0.25 if record.evidence_id in self.graph_evidence_ids(question) else 0.0
        return super()._score(record, question) + 0.5 + graph_bonus
