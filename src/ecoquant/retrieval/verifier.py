"""Temporal KG results checked by a distinct source-time verifier.

Verifies temporal validity and source-time constraints of retrieved evidence.
This is a deterministic verification stage, not a learned model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph
from ecoquant.evidence_graph.models import Document

from .base import CorpusRecord, Question, RetrievalMetadata
from .reranker import TemporalKGRerankRetriever


def _source_verifier(record: CorpusRecord, question: Question) -> str:
    """Verify temporal validity and source-time constraints.

    Returns:
        - "time_verified": record is valid for the requested time
        - "invalid_for_requested_time": record's valid time exceeds requested time
        - "published_after_source_cutoff": record was published after source cutoff
    """
    if record.valid_time > question.valid_at:
        return "invalid_for_requested_time"
    if record.source_time is None:
        return "missing_source_time"
    if record.source_time > question.effective_source_cutoff:
        return "published_after_source_cutoff"
    return "time_verified"


class TemporalKGVerifyRetriever(TemporalKGRerankRetriever):
    """Temporal KG retrieval with reranking and source-time verification."""

    method_name = "temporal_kg_verify"
    metadata = RetrievalMetadata(
        method_id="temporal_kg_verify",
        implementation_mode="production",
        backend="source-time-verifier",
        model_name="deterministic-temporal-verifier",
        model_revision="1.0.0",
        uses_graph=True,
        uses_temporal_filter=True,
        uses_reranker=True,
        uses_verification=True,
        backend_status="production_unavailable",
    )

    def __init__(
        self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None
    ) -> None:
        super().__init__(corpus, cutoff=cutoff, graph=graph)
        self.verifier: Callable[[CorpusRecord, Question], str] = _source_verifier

    def _verification_status(self, record: CorpusRecord, question: Question) -> str:
        """Apply source-time verification to the record."""
        if record.source_time is None:
            try:
                linked = self.graph.node(record.evidence_id)
            except KeyError:
                linked = None
            if isinstance(linked, Document) and linked.source_time is not None:
                record = replace(record, source_time=linked.source_time)
        return self.verifier(record, question)
