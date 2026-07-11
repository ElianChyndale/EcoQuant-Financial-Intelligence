"""Temporal KG retrieval with local consistency status annotations."""

from __future__ import annotations

from .base import CorpusRecord
from .reranker import TemporalKGRerankRetriever


class TemporalKGVerifyRetriever(TemporalKGRerankRetriever):
    method_name = "temporal_kg_verify"

    def _verification_status(self, record: CorpusRecord) -> str:
        return "time_verified" if record.valid_time <= self.cutoff else "unverified"
