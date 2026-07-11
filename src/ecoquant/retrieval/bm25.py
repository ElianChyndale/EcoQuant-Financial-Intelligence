"""Deterministic BM25-style lexical baseline."""

from __future__ import annotations

from .base import BaseRetriever, CorpusRecord, Question, RetrievalMetadata, _terms


class BM25Retriever(BaseRetriever):
    method_name = "bm25"
    metadata = RetrievalMetadata("bm25", "fixture", "deterministic-local", "bm25-tokenizer", "local-fixture-20260710", False, True, False, False)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        query_terms = _terms(question.query)
        document_terms = _terms(record.text)
        if not query_terms:
            return 0.0
        matched = len(query_terms & document_terms)
        return matched / (len(document_terms) + 0.5) + (0.25 if str(record.valid_time.year) in query_terms else 0.0)
