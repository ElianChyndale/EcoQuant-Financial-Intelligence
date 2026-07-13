"""Dense retrieval using sentence-transformers with pinned model.

Uses cosine similarity between query and document embeddings for semantic retrieval.
Model is pinned to a specific revision for reproducibility.

In production mode, raises an error if the model cannot be loaded.
In fixture mode, falls back to a deterministic token-overlap proxy.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import numpy as np

from .base import BaseRetriever, CorpusRecord, Question, RetrievalMetadata


@dataclass(frozen=True)
class ModelPin:
    """Immutable model identification for reproducibility."""
    name: str
    revision: str | None


# Pinned model for reproducibility
DENSE_MODEL = ModelPin(
    "sentence-transformers/all-MiniLM-L6-v2",
    "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


class DenseRetriever(BaseRetriever):
    """Dense retrieval using sentence-transformers embeddings.

    In production mode, the model MUST load successfully. If the model cannot
    be loaded, a RuntimeError is raised rather than silently degrading.
    """

    method_name = "dense"
    model = DENSE_MODEL
    metadata = RetrievalMetadata(
        method_id="dense",
        implementation_mode="production",
        backend="sentence-transformers",
        model_name=DENSE_MODEL.name,
        model_revision=DENSE_MODEL.revision,
        uses_graph=False,
        uses_temporal_filter=True,
        uses_reranker=False,
        uses_verification=False,
        backend_status="production_unavailable",
    )

    def __init__(self, corpus: Iterable[CorpusRecord], *, cutoff: date) -> None:
        super().__init__(corpus, cutoff=cutoff)
        self._embedder = None
        self._corpus_embeddings: np.ndarray | None = None
        self._model_loaded = False
        self._successful_model_inference = False
        self._init_embeddings()

    def _init_embeddings(self) -> None:
        """Initialize sentence-transformer model and compute corpus embeddings.

        In production mode, raises RuntimeError if the model cannot be loaded.
        This prevents silent degradation of production results.
        """
        try:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(
                DENSE_MODEL.name,
                revision=DENSE_MODEL.revision,
            )
            # Compute embeddings for all corpus texts
            texts = [record.text for record in self.corpus]
            self._corpus_embeddings = self._embedder.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            self._model_loaded = True
        except Exception as e:
            # In production mode, fail clearly rather than silently degrade
            raise RuntimeError(
                f"Failed to load production dense model '{DENSE_MODEL.name}' "
                f"revision '{DENSE_MODEL.revision}': {e}. "
                f"A production run must not silently fall back to proxy scoring."
            ) from e

    def _score(self, record: CorpusRecord, question: Question) -> float:
        """Score using cosine similarity of embeddings."""
        if not self._model_loaded or self._embedder is None or self._corpus_embeddings is None:
            raise RuntimeError(
                "Dense retriever model not loaded. "
                "This should not happen in production mode."
            )

        # Find index of this record in the corpus
        record_idx = None
        for idx, corpus_record in enumerate(self.corpus):
            if corpus_record.evidence_id == record.evidence_id:
                record_idx = idx
                break
        if record_idx is None:
            return 0.0

        # Encode query and compute similarity
        query_embedding = self._embedder.encode(
            [question.query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )[0]
        self._successful_model_inference = True
        return _cosine_similarity(query_embedding, self._corpus_embeddings[record_idx])

    def _execution_proof_complete(self) -> bool:
        return (
            self._model_loaded
            and self._successful_model_inference
            and self._embedder is not None
            and self._corpus_embeddings is not None
        )

    def _begin_execution(self) -> None:
        self._successful_model_inference = False
