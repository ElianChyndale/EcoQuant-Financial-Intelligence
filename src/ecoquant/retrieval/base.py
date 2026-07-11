"""Shared, label-free retrieval interfaces for the frozen benchmark."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class CorpusRecord:
    """A local evidence fixture available to every comparable method."""

    evidence_id: str
    issuer: str
    valid_time: date
    text: str
    numeric_value: float | None = None


@dataclass(frozen=True)
class Question:
    """Retrieval input intentionally limited to query and temporal context."""

    question_id: str
    issuer: str
    query: str
    cutoff: date


@dataclass(frozen=True)
class RetrievalResult:
    method: str
    question_id: str
    evidence_id: str
    rank: int
    score: float
    valid_time_match: bool
    verification_status: str


class Retriever(Protocol):
    method_name: str
    corpus: tuple[CorpusRecord, ...]
    cutoff: date

    def retrieve(self, question: Question, top_k: int = 5) -> tuple[RetrievalResult, ...]: ...


class BaseRetriever:
    """Common deterministic ranking and temporal accounting implementation."""

    method_name = "base"
    uses_temporal_filter = True

    def __init__(self, corpus: Iterable[CorpusRecord], *, cutoff: date, graph: object | None = None) -> None:
        self.corpus = tuple(corpus)
        self.cutoff = cutoff
        self.graph = graph
        identifiers = [record.evidence_id for record in self.corpus]
        if not self.corpus:
            raise ValueError("corpus must contain at least one record")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("corpus evidence_id values must be unique")

    def retrieve(self, question: Question, top_k: int = 5) -> tuple[RetrievalResult, ...]:
        if top_k != 5:
            raise ValueError("comparable retrieval uses a fixed top_k=5")
        if question.cutoff != self.cutoff:
            raise ValueError("question cutoff must equal the shared method cutoff")

        candidates = [record for record in self.corpus if self._include(record, question)]
        ranked = sorted(
            ((self._score(record, question), record) for record in candidates),
            key=lambda item: (-item[0], item[1].evidence_id),
        )[:top_k]
        return tuple(
            RetrievalResult(
                method=self.method_name,
                question_id=question.question_id,
                evidence_id=record.evidence_id,
                rank=rank,
                score=score,
                valid_time_match=record.valid_time <= question.cutoff,
                verification_status=self._verification_status(record),
            )
            for rank, (score, record) in enumerate(ranked, start=1)
        )

    def _include(self, record: CorpusRecord, question: Question) -> bool:
        return (not self.uses_temporal_filter or record.valid_time <= question.cutoff) and record.issuer == question.issuer

    def _score(self, record: CorpusRecord, question: Question) -> float:
        query_terms = _terms(question.query)
        record_terms = _terms(record.text)
        overlap = len(query_terms & record_terms)
        year_bonus = 0.25 if str(record.valid_time.year) in query_terms else 0.0
        return float(overlap) + year_bonus

    def _verification_status(self, record: CorpusRecord) -> str:
        return "unverified"

    def graph_evidence_ids(self, question: Question) -> frozenset[str]:
        """Read temporal graph evidence only; it contains no evaluation labels."""

        evidence_valid_at = getattr(self.graph, "evidence_valid_at", None)
        if not callable(evidence_valid_at):
            return frozenset()
        return frozenset(
            evidence.document_id
            for evidence in evidence_valid_at(question.issuer, question.cutoff)
            if isinstance(getattr(evidence, "document_id", None), str)
        )


def _terms(text: str) -> frozenset[str]:
    return frozenset("".join(character if character.isalnum() else " " for character in text.lower()).split())


def all_retrievers(
    corpus: Sequence[CorpusRecord], *, cutoff: date, graph: object | None = None
) -> tuple[Retriever, ...]:
    """Construct the six methods over precisely the same frozen inputs."""

    from .bm25 import BM25Retriever
    from .dense import DenseRetriever
    from .kg import StaticKGRetriever, TemporalKGRetriever
    from .reranker import TemporalKGRerankRetriever
    from .verifier import TemporalKGVerifyRetriever

    return (
        BM25Retriever(corpus, cutoff=cutoff, graph=graph),
        DenseRetriever(corpus, cutoff=cutoff, graph=graph),
        StaticKGRetriever(corpus, cutoff=cutoff, graph=graph),
        TemporalKGRetriever(corpus, cutoff=cutoff, graph=graph),
        TemporalKGRerankRetriever(corpus, cutoff=cutoff, graph=graph),
        TemporalKGVerifyRetriever(corpus, cutoff=cutoff, graph=graph),
    )
