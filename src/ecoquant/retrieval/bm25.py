"""Genuine BM25 retrieval using rank-bm25 library.

Uses the Okapi BM25 algorithm with tokenized corpus for lexical retrieval.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from rank_bm25 import BM25Okapi

from .base import BaseRetriever, CorpusRecord, Question, RetrievalMetadata


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    return [
        token.lower()
        for token in "".join(
            character if character.isalnum() or character.isspace() else " "
            for character in text
        ).split()
        if token
    ]


class BM25Retriever(BaseRetriever):
    """Genuine BM25 retrieval using rank-bm25 Okapi implementation."""

    method_name = "bm25"
    metadata = RetrievalMetadata(
        method_id="bm25",
        implementation_mode="production",
        backend="rank-bm25",
        model_name="bm25-okapi",
        model_revision="0.2.2",
        uses_graph=False,
        uses_temporal_filter=True,
        uses_reranker=False,
        uses_verification=False,
    )

    def __init__(self, corpus: Iterable[CorpusRecord], *, cutoff: date) -> None:
        super().__init__(corpus, cutoff=cutoff)
        # Build BM25 index from corpus texts
        self._tokenized_corpus = [_tokenize(record.text) for record in self.corpus]
        self._bm25 = BM25Okapi(self._tokenized_corpus)

    def _score(self, record: CorpusRecord, question: Question) -> float:
        """Score using BM25 Okapi algorithm."""
        query_tokens = _tokenize(question.query)
        # Find index of this record in the corpus
        record_idx = None
        for idx, corpus_record in enumerate(self.corpus):
            if corpus_record.evidence_id == record.evidence_id:
                record_idx = idx
                break
        if record_idx is None:
            return 0.0

        # Get BM25 score for this document
        scores = self._bm25.get_scores(query_tokens)
        return float(scores[record_idx])
