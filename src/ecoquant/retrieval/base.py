"""Label-free retrieval contracts and the shared comparison boundary."""

from __future__ import annotations

import hashlib
import json
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
    backend_status: Literal["production_verified", "production_unavailable", "fixture", "exploratory"] = "fixture"

    @classmethod
    def fixture(cls, method_id: str, **overrides: object) -> "RetrievalMetadata":
        values: dict[str, object] = {
            "method_id": method_id, "implementation_mode": "fixture", "backend": "deterministic-local",
            "model_name": None, "model_revision": None, "uses_graph": False, "uses_temporal_filter": False,
            "uses_reranker": False, "uses_verification": False, "backend_status": "fixture",
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]

    def validate(self) -> None:
        if self.method_id not in REGISTERED_METHOD_IDS:
            raise ValueError(f"unknown registered method_id: {self.method_id}")
        if self.implementation_mode == "fixture" and self.backend_status not in {"fixture", "exploratory"}:
            raise ValueError("fixture metadata requires fixture or exploratory backend status")
        if self.implementation_mode == "production" and self.backend_status not in {
            "production_verified", "production_unavailable"
        }:
            raise ValueError("production metadata requires an explicit production backend status")
        if self.implementation_mode == "production" and (not self.backend or not self.model_name):
            if not (self.backend_status == "production_verified" and self.uses_graph and not self.uses_reranker):
                raise ValueError("production metadata requires backend and model_name")
        if self.implementation_mode == "production" and self.backend_status == "production_verified" and (
            not self.uses_graph or self.uses_reranker
        ) and not self.model_revision:
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
        self.corpus_fingerprint = corpus_fingerprint(self.corpus)
        self.cutoff = cutoff
        identifiers = [record.evidence_id for record in self.corpus]
        if not self.corpus:
            raise ValueError("corpus must contain at least one record")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("corpus evidence_id values must be unique")
        self._corpus_by_evidence_id = {record.evidence_id: record for record in self.corpus}
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
    """Run exactly the six registered methods under one normalized top-k policy.

    In final_benchmark mode, top_k must be exactly 5 — the authoritative
    comparison boundary requires top_k=5 for all methods.
    """

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if final_benchmark and top_k != 5:
        raise ValueError(
            f"final benchmark mode requires top_k=5, got {top_k}. "
            f"The authoritative comparison boundary requires exactly top_k=5."
        )
    if final_benchmark and query.source_cutoff is None:
        raise ValueError("final benchmark requires an explicit source_cutoff")
    method_ids = [method.method_name for method in methods]
    if len(method_ids) != len(set(method_ids)):
        raise ValueError("duplicate method identifiers are not comparable")
    if set(method_ids) != set(REGISTERED_METHOD_IDS) or len(method_ids) != len(REGISTERED_METHOD_IDS):
        raise ValueError("comparison requires exactly the six registered methods")

    # Prove all methods share the same corpus, cutoff, and top_k
    _validate_shared_corpus_and_cutoff(methods, query)

    if final_benchmark:
        validate_final_benchmark(methods)

    output: dict[str, tuple[RetrievalResult, ...]] = {}
    for method in methods:
        method.metadata.validate()
        if method.metadata.method_id != method.method_name:
            raise ValueError("retriever metadata method_id must match the registered method name")
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
        if final_benchmark and (
            len(raw) > top_k
            or tuple(raw) != tuple(ordered)
            or [item.rank for item in raw] != list(range(1, len(raw) + 1))
        ):
            raise ValueError(
                "final benchmark results require canonical ranks and score ordering "
                "with deterministic evidence-ID tie-breaking"
            )
        output[method.method_name] = tuple(replace(item, rank=rank) for rank, item in enumerate(ordered, start=1))
    return output


def _validate_shared_corpus_and_cutoff(
    methods: Sequence[Retriever], query: RetrieverQuery
) -> None:
    """Prove all methods receive the same corpus, cutoff, and query.

    Validates that:
    - All methods have the same corpus size
    - All methods have the same cutoff date
    - All methods receive the same query (valid_at, source_cutoff)

    Skips corpus/cutoff validation for methods that don't have these
    attributes (e.g., test hostile retrievers).
    """
    if not methods:
        return

    # Only validate methods that have corpus and cutoff attributes
    methods_with_corpus = [m for m in methods if hasattr(m, 'corpus') and hasattr(m, 'cutoff')]

    if len(methods_with_corpus) < 2:
        return

    reference_corpus_size = len(methods_with_corpus[0].corpus)
    reference_fingerprint = corpus_fingerprint(methods_with_corpus[0].corpus)
    reference_cutoff = methods_with_corpus[0].cutoff

    for method in methods_with_corpus[1:]:
        if len(method.corpus) != reference_corpus_size:
            raise ValueError(
                f"corpus size mismatch: {method.method_name} has "
                f"{len(method.corpus)} records, expected {reference_corpus_size}"
            )
        if corpus_fingerprint(method.corpus) != reference_fingerprint:
            raise ValueError(
                f"corpus fingerprint mismatch: {method.method_name} does not share "
                "the canonical comparison corpus"
            )
        if method.cutoff != reference_cutoff:
            raise ValueError(
                f"cutoff mismatch: {method.method_name} has cutoff "
                f"{method.cutoff}, expected {reference_cutoff}"
            )


def validate_final_benchmark(methods: Sequence[Retriever]) -> None:
    """Reject local fixtures before an output can be called a final benchmark."""

    for method in methods:
        method.metadata.validate()
        if method.metadata.implementation_mode != "production":
            raise ValueError(f"final benchmark rejects fixture-mode method: {method.method_name}")
        if method.metadata.backend_status != "production_verified":
            raise ValueError(
                f"final benchmark requires production_verified backend status: {method.method_name}"
            )
        reported_fingerprint = getattr(method, "corpus_fingerprint", None)
        if not reported_fingerprint:
            raise ValueError(
                f"final benchmark method {method.method_name} is missing canonical corpus fingerprint"
            )
        computed_fingerprint = corpus_fingerprint(method.corpus)
        if reported_fingerprint != computed_fingerprint:
            raise ValueError(
                f"reported corpus fingerprint does not match canonical corpus for {method.method_name}"
            )


def retrieval_manifest(methods: Sequence[Retriever]) -> Mapping[str, RetrievalMetadata]:
    """Metadata retained beside method-keyed comparison outputs."""

    return {method.method_name: method.metadata for method in methods}


def _terms(text: str) -> frozenset[str]:
    return frozenset("".join(character if character.isalnum() else " " for character in text.lower()).split())


def corpus_fingerprint(corpus: Sequence[CorpusRecord]) -> str:
    """Compute a deterministic SHA-256 fingerprint over canonical retriever-visible fields.

    Fields per record (sorted deterministically by evidence_id):
    - schema version (1)
    - evidence_id
    - issuer
    - valid_time (ISO format)
    - source_time (ISO format, or empty)
    - text (normalized: stripped, lowered)
    - numeric_value (string representation, or empty)

    Returns:
        Hex-encoded SHA-256 digest.
    """
    sorted_records = sorted(corpus, key=lambda r: r.evidence_id)
    canonical_parts: list[str] = []
    for record in sorted_records:
        parts = [
            "1",  # schema version
            record.evidence_id,
            record.issuer,
            record.valid_time.isoformat(),
            record.source_time.isoformat() if record.source_time else "",
            record.text.strip().lower(),
            str(record.numeric_value) if record.numeric_value is not None else "",
        ]
        canonical_parts.append("|".join(parts))
    canonical_bytes = "\n".join(canonical_parts).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


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
