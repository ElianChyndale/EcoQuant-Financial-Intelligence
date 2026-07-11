"""Temporal KG method slot with an honest deterministic local reranking proxy."""

from __future__ import annotations

from .base import CorpusRecord, Question
from .dense import ModelPin
from .kg import TemporalKGRetriever


RERANKER_MODEL = ModelPin("BAAI/bge-reranker-base", "local-fixture-20260710")


class TemporalKGRerankRetriever(TemporalKGRetriever):
    method_name = "temporal_kg_rerank"
    model = RERANKER_MODEL

    def _score(self, record: CorpusRecord, question: Question) -> float:
        base_score = super()._score(record, question)
        exact_period_bonus = 0.5 if str(record.valid_time.year) in question.query else 0.0
        return base_score + exact_period_bonus
