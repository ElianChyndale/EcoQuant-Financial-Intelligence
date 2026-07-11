"""Dense-method slot with a deterministic local proxy, not downloaded weights.

The pinned model identifies the intended experiment artifact. This module does
not claim to execute that artifact: it intentionally uses a local, reproducible
similarity proxy until an artifact-validated offline model is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import BaseRetriever, CorpusRecord, Question, RetrievalMetadata, _terms


@dataclass(frozen=True)
class ModelPin:
    name: str
    revision: str


DENSE_MODEL = ModelPin("sentence-transformers/all-MiniLM-L6-v2", "local-fixture-20260710")


class DenseRetriever(BaseRetriever):
    method_name = "dense"
    model = DENSE_MODEL
    metadata = RetrievalMetadata("dense", "fixture", "deterministic-local", DENSE_MODEL.name, DENSE_MODEL.revision, False, True, False, False)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        query_terms = _terms(question.query)
        document_terms = _terms(record.text)
        union = query_terms | document_terms
        similarity = len(query_terms & document_terms) / len(union) if union else 0.0
        return similarity + (0.25 if str(record.valid_time.year) in query_terms else 0.0)
