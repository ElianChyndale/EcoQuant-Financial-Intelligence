"""Temporal KG results passed through a distinct deterministic reranker."""

from __future__ import annotations

from collections.abc import Callable

from .base import CorpusRecord, Question, RetrievalMetadata
from .dense import ModelPin
from .kg import TemporalKGRetriever

RERANKER_MODEL = ModelPin("BAAI/bge-reranker-base", "local-fixture-20260710")


def _period_reranker(record: CorpusRecord, question: Question, score: float) -> float:
    return score + (0.5 if str(record.valid_time.year) in question.query else 0.0)


class TemporalKGRerankRetriever(TemporalKGRetriever):
    method_name = "temporal_kg_rerank"
    model = RERANKER_MODEL
    metadata = RetrievalMetadata("temporal_kg_rerank", "fixture", "temporal-evidence-graph", RERANKER_MODEL.name, RERANKER_MODEL.revision, True, True, True, False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.reranker: Callable[[CorpusRecord, Question, float], float] = _period_reranker

    def _score(self, record: CorpusRecord, question: Question) -> float:
        return self.reranker(record, question, super()._score(record, question))
