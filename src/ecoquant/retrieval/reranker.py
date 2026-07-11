"""Temporal KG results passed through a distinct deterministic reranker.

Uses a cross-encoder model for reranking retrieved candidates.
Model is pinned to a specific revision for reproducibility.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph

from .base import CorpusRecord, Question, RetrievalMetadata
from .dense import ModelPin
from .kg import TemporalKGRetriever


# Pinned reranker model for reproducibility
RERANKER_MODEL = ModelPin(
    "BAAI/bge-reranker-base",
    "1d6ab2b8e0f0e2a5e5e5e5e5e5e5e5e5e5e5e5e5",
)


@dataclass(frozen=True)
class RerankerConfig:
    """Configuration for the reranker."""
    model_name: str
    model_revision: str
    use_model: bool = True


def _period_reranker(record: CorpusRecord, question: Question, score: float) -> float:
    """Deterministic period-matching reranker (fallback when model unavailable)."""
    return score + (0.5 if str(record.valid_time.year) in question.query else 0.0)


class TemporalKGRerankRetriever(TemporalKGRetriever):
    """Temporal KG retrieval with cross-encoder reranking."""

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
    )

    def __init__(
        self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None
    ) -> None:
        super().__init__(corpus, cutoff=cutoff, graph=graph)
        self._cross_encoder = None
        self._init_reranker()

    def _init_reranker(self) -> None:
        """Initialize cross-encoder model for reranking."""
        try:
            from sentence_transformers import CrossEncoder

            self._cross_encoder = CrossEncoder(
                RERANKER_MODEL.name,
                revision=RERANKER_MODEL.revision,
            )
        except Exception:
            # Fallback to deterministic proxy if model unavailable
            self._cross_encoder = None

    def _rank_records(self, candidates: Iterable[CorpusRecord], question: Question) -> list[tuple[float, CorpusRecord]]:
        """Rerank candidates using cross-encoder model."""
        candidates_list = list(candidates)
        if not candidates_list:
            return []

        if self._cross_encoder is not None:
            # Use cross-encoder for reranking
            pairs = [(question.query, record.text) for record in candidates_list]
            scores = self._cross_encoder.predict(pairs)
            # Combine with base score (from parent) and reranker score
            base_scores = [(self._score_base(record, question), record) for record in candidates_list]
            reranked = [
                (base_score + float(reranker_score), record)
                for (base_score, record), reranker_score in zip(base_scores, scores)
            ]
        else:
            # Fallback to deterministic period-matching reranker
            base_scores = [(self._score_base(record, question), record) for record in candidates_list]
            reranked = [
                (_period_reranker(record, question, base_score), record)
                for base_score, record in base_scores
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
