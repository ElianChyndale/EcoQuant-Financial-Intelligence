"""Label-free retrieval contracts and the shared comparison boundary."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite
from typing import Literal, Protocol

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph


REGISTERED_METHOD_IDS = (
    "bm25", "dense", "static_kg", "temporal_kg", "temporal_kg_rerank", "temporal_kg_verify",
)


@dataclass(frozen=True)
class CorpusRecord:
    """Source-derived evidence available to every comparable method."""

    evidence_id: str
    issuer: str
    valid_time: date
    text: str
    numeric_value: float | None = None
    source_time: date | None = None


@dataclass(frozen=True)
class RetrieverQuery:
    """The only query shape accepted by retrievers; it carries no gold data."""

    question_id: str
    issuer: str
    query: str
    cutoff: date
    source_cutoff: date | None = None

    @property
    def valid_at(self) -> date:
        return self.cutoff

    @property
    def effective_source_cutoff(self) -> date:
        return self.source_cutoff or self.valid_at


# Kept as a compatibility name for the frozen Task 5 fixture.
Question = RetrieverQuery


@dataclass(frozen=True)
class RetrievalResult:
    method: str
    question_id: str
    evidence_id: str
    rank: int
    score: float
    valid_time_match: bool
    verification_status: str


@dataclass(frozen=True)
class RetrievalMetadata:
    """Immutable implementation provenance for a method result or manifest."""

    method_id: str
    implementation_mode: Literal["production", "fixture"]
    backend: str
    model_name: str | None
    model_revision: str | None
    uses_graph: bool
    uses_temporal_filter: bool
    uses_reranker: bool
    uses_verification: bool

    @classmethod
    def fixture(cls, method_id: str, **overrides: object) -> "RetrievalMetadata":
        values: dict[str, object] = {
            "method_id": method_id, "implementation_mode": "fixture", "backend": "deterministic-local",
            "model_name": None, "model_revision": None, "uses_graph": False, "uses_temporal_filter": False,
            "uses_reranker": False, "uses_verification": False,
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]

    def validate(self) -> None:
        if self.method_id not in REGISTERED_METHOD_IDS:
            raise ValueError(f"unknown registered method_id: {self.method_id}")
        if self.implementation_mode == "production" and (not self.backend or not self.model_name or not self.model_revision):
            raise ValueError("production metadata requires backend, model_name, and model_revision")


class Retriever(Protocol):
    method_name: str
    corpus: tuple[CorpusRecord, ...]
    cutoff: date
    metadata: RetrievalMetadata

    def retrieve(self, question: RetrieverQuery, top_k: int = 5) -> tuple[RetrievalResult, ...]: ...


class BaseRetriever:
    """Common deterministic ranking and label-free query validation."""

    method_name = "base"
    uses_temporal_filter = True
    metadata = RetrievalMetadata.fixture("bm25")

    def __init__(self, corpus: Iterable[CorpusRecord], *, cutoff: date) -> None:
        self.corpus = tuple(corpus)
        self.cutoff = cutoff
        identifiers = [record.evidence_id for record in self.corpus]
        if not self.corpus:
            raise ValueError("corpus must contain at least one record")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("corpus evidence_id values must be unique")
        self.metadata.validate()

    def retrieve(self, question: RetrieverQuery, top_k: int = 5) -> tuple[RetrievalResult, ...]:
        if type(question) is not RetrieverQuery:
            raise TypeError("retrieval accepts only RetrieverQuery")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if question.valid_at != self.cutoff:
            raise ValueError("question cutoff must equal the shared method cutoff")
        ranked = self._rank_records(self._candidate_records(question), question)
        return tuple(
            RetrievalResult(self.method_name, question.question_id, record.evidence_id, rank, score,
                            record.valid_time <= question.valid_at, self._verification_status(record, question))
            for rank, (score, record) in enumerate(ranked[:top_k], start=1)
        )

    def _candidate_records(self, question: RetrieverQuery) -> list[CorpusRecord]:
        return [record for record in self.corpus if self._include(record, question)]

    def _rank_records(self, candidates: Iterable[CorpusRecord], question: RetrieverQuery) -> list[tuple[float, CorpusRecord]]:
        return sorted(((self._score(record, question), record) for record in candidates), key=lambda item: (-item[0], item[1].evidence_id))

    def _include(self, record: CorpusRecord, question: RetrieverQuery) -> bool:
        return (not self.uses_temporal_filter or record.valid_time <= question.valid_at) and record.issuer == question.issuer

    def _score(self, record: CorpusRecord, question: RetrieverQuery) -> float:
        query_terms = _terms(question.query)
        record_terms = _terms(record.text)
        return float(len(query_terms & record_terms)) + (0.25 if str(record.valid_time.year) in query_terms else 0.0)

    def _verification_status(self, record: CorpusRecord, question: RetrieverQuery) -> str:
        return "unverified"


def compare_retrievers(
    methods: Sequence[Retriever], query: RetrieverQuery, *, top_k: int = 5, final_benchmark: bool = False
) -> dict[str, tuple[RetrievalResult, ...]]:
    """Run exactly the six registered methods under one normalized top-k policy."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    method_ids = [method.method_name for method in methods]
    if len(method_ids) != len(set(method_ids)):
        raise ValueError("duplicate method identifiers are not comparable")
    if set(method_ids) != set(REGISTERED_METHOD_IDS) or len(method_ids) != len(REGISTERED_METHOD_IDS):
        raise ValueError("comparison requires exactly the six registered methods")
    if final_benchmark:
        validate_final_benchmark(methods)
    output: dict[str, tuple[RetrievalResult, ...]] = {}
    for method in methods:
        method.metadata.validate()
        raw = tuple(method.retrieve(query, top_k=top_k))
        if any(result.method != method.method_name for result in raw):
            raise ValueError("retriever returned a result for another method")
        if any(result.question_id != query.question_id for result in raw):
            raise ValueError("retriever returned a result for another question_id")
        if len({result.evidence_id for result in raw}) != len(raw):
            raise ValueError("retriever results must have unique evidence IDs")
        if any(not isfinite(result.score) for result in raw):
            raise ValueError("retriever result scores must be finite")
        ordered = sorted(raw, key=lambda item: (-item.score, item.evidence_id))[:top_k]
        output[method.method_name] = tuple(replace(item, rank=rank) for rank, item in enumerate(ordered, start=1))
    return output


def validate_final_benchmark(methods: Sequence[Retriever]) -> None:
    """Reject local fixtures before an output can be called a final benchmark."""

    for method in methods:
        method.metadata.validate()
        if method.metadata.implementation_mode != "production":
            raise ValueError(f"final benchmark rejects fixture-mode method: {method.method_name}")


def retrieval_manifest(methods: Sequence[Retriever]) -> Mapping[str, RetrievalMetadata]:
    """Metadata retained beside method-keyed comparison outputs."""

    return {method.method_name: method.metadata for method in methods}


def _terms(text: str) -> frozenset[str]:
    return frozenset("".join(character if character.isalnum() else " " for character in text.lower()).split())


def all_retrievers(
    corpus: Sequence[CorpusRecord], *, cutoff: date, graph: TemporalEvidenceGraph | None = None,
    mode: str = "production"
) -> tuple[Retriever, ...]:
    """Construct the six methods over the same corpus and cutoff.

    Args:
        corpus: The frozen corpus of evidence records.
        cutoff: The temporal cutoff date.
        graph: Optional temporal evidence graph for KG methods.
        mode: "production" for real backends, "fixture" for deterministic testing.
    """

    from .bm25 import BM25Retriever
    from .dense import DenseRetriever
    from .kg import StaticKGRetriever, TemporalKGRetriever
    from .reranker import TemporalKGRerankRetriever
    from .verifier import TemporalKGVerifyRetriever

    if mode == "fixture":
        # Return fixture-mode retrievers for unit testing
        from .fixture import (
            FixtureBM25Retriever,
            FixtureDenseRetriever,
            FixtureStaticKGRetriever,
            FixtureTemporalKGRetriever,
            FixtureTemporalKGRerankRetriever,
            FixtureTemporalKGVerifyRetriever,
        )
        return (
            FixtureBM25Retriever(corpus, cutoff=cutoff),
            FixtureDenseRetriever(real_bm25=None, corpus=corpus, cutoff=cutoff),
            FixtureStaticKGRetriever(corpus, cutoff=cutoff, graph=graph),
            FixtureTemporalKGRetriever(corpus, cutoff=cutoff, graph=graph),
            FixtureTemporalKGRerankRetriever(corpus, cutoff=cutoff, graph=graph),
            FixtureTemporalKGVerifyRetriever(corpus, cutoff=cutoff, graph=graph),
        )

    # Return production-mode retrievers
    return (
        BM25Retriever(corpus, cutoff=cutoff),
        DenseRetriever(corpus, cutoff=cutoff),
        StaticKGRetriever(corpus, cutoff=cutoff, graph=graph),
        TemporalKGRetriever(corpus, cutoff=cutoff, graph=graph),
        TemporalKGRerankRetriever(corpus, cutoff=cutoff, graph=graph),
        TemporalKGVerifyRetriever(corpus, cutoff=cutoff, graph=graph),
    )
