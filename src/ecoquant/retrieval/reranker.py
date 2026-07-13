"""Temporal KG results passed through a distinct deterministic reranker.

Uses a cross-encoder model for reranking retrieved candidates.
Model is pinned to a specific revision for reproducibility.

In production mode, raises an error if the model cannot be loaded.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph

from .base import CorpusRecord, Question, RetrievalMetadata
from .dense import ModelPin
from .kg import TemporalKGRetriever


# Pinned reranker model for reproducibility
RERANKER_MODEL = ModelPin(
    "BAAI/bge-reranker-base",
    None,
)


class TemporalKGRerankRetriever(TemporalKGRetriever):
    """Temporal KG retrieval with cross-encoder reranking.

    In production mode, the cross-encoder model MUST load successfully.
    If the model cannot be loaded, a RuntimeError is raised rather than
    silently degrading to proxy scoring.
    """

    method_name = "temporal_kg_rerank"
    model = RERANKER_MODEL
    metadata = RetrievalMetadata(
        method_id="temporal_kg_rerank",
        implementation_mode="production",
        backend="cross-encoder",
        model_name=RERANKER_MODEL.name,
        model_revision=RERANKER_MODEL.revision,
        uses_graph=True,
        uses_temporal_filter=True,
        uses_reranker=True,
        uses_verification=False,
        backend_status="production_unavailable",
    )

    def __init__(
        self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None
    ) -> None:
        super().__init__(corpus, cutoff=cutoff, graph=graph)
        self._cross_encoder = None
        self._model_loaded = False
        self._init_reranker()

    def _init_reranker(self) -> None:
        """Initialize cross-encoder model for reranking.

        In production mode, raises RuntimeError if the model cannot be loaded.
        This prevents silent degradation of production results.
        """
        if RERANKER_MODEL.revision is None:
            raise RuntimeError(
                f"Failed to load production reranker model '{RERANKER_MODEL.name}': "
                "no verified immutable revision is configured. "
                "A production run must not silently fall back to proxy scoring."
            )
        try:
            from sentence_transformers import CrossEncoder

            self._cross_encoder = CrossEncoder(
                RERANKER_MODEL.name,
                revision=RERANKER_MODEL.revision,
            )
            self._model_loaded = True
            self.metadata = replace(self.metadata, backend_status="production_verified")
        except Exception as e:
            # In production mode, fail clearly rather than silently degrade
            raise RuntimeError(
                f"Failed to load production reranker model '{RERANKER_MODEL.name}' "
                f"revision '{RERANKER_MODEL.revision}': {e}. "
                f"A production run must not silently fall back to proxy scoring."
            ) from e

    def _rank_records(self, candidates: Iterable[CorpusRecord], question: Question) -> list[tuple[float, CorpusRecord]]:
        """Rerank candidates using cross-encoder model."""
        candidates_list = list(candidates)
        if not candidates_list:
            return []

        if not self._model_loaded or self._cross_encoder is None:
            raise RuntimeError(
                "Reranker model not loaded. "
                "This should not happen in production mode."
            )

        # Use cross-encoder for reranking
        pairs = [(question.query, record.text) for record in candidates_list]
        scores = self._cross_encoder.predict(pairs)
        # Combine with base score (from parent) and reranker score
        base_scores = [(self._score_base(record, question), record) for record in candidates_list]
        reranked = [
            (base_score + float(reranker_score), record)
            for (base_score, record), reranker_score in zip(base_scores, scores)
        ]

        return sorted(reranked, key=lambda item: (-item[0], item[1].evidence_id))

    def _score_base(self, record: CorpusRecord, question: Question) -> float:
        """Get base score from parent TemporalKGRetriever."""
        return super()._score(record, question)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        """Score is computed during reranking, not individually."""
        # This method is called by parent's _rank_records, but we override
        # _rank_records directly, so this is not used
        return super()._score(record, question)
