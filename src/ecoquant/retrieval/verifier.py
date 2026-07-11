"""Temporal KG results checked by a distinct source-time verifier."""

from __future__ import annotations

from collections.abc import Callable

from .base import CorpusRecord, Question, RetrievalMetadata
from .reranker import TemporalKGRerankRetriever


def _source_verifier(record: CorpusRecord, question: Question) -> str:
    return "time_verified" if record.valid_time <= question.cutoff else "unverified"


class TemporalKGVerifyRetriever(TemporalKGRerankRetriever):
    method_name = "temporal_kg_verify"
    metadata = RetrievalMetadata("temporal_kg_verify", "fixture", "temporal-evidence-graph", "source-time-verifier", "local-fixture-20260710", True, True, True, True)

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.verifier: Callable[[CorpusRecord, Question], str] = _source_verifier

    def _verification_status(self, record: CorpusRecord, question: Question) -> str:
        return self.verifier(record, question)
