"""Label-free retrieval contracts and the shared comparison boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from math import isfinite
from types import MappingProxyType
from typing import Literal, Protocol

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph


REGISTERED_METHOD_IDS = (
    "bm25", "dense", "static_kg", "temporal_kg", "temporal_kg_rerank", "temporal_kg_verify",
)

CORPUS_FINGERPRINT_SCHEMA_VERSION = 3
CORPUS_RECORD_SCHEMA_VERSION = "retrieval-corpus-record.v3"
CorpusNumericValue = int | Decimal | float | str | None

NON_PRODUCTION_BACKEND_IDS = frozenset({
    "deterministic-local", "exploratory", "fixture", "placeholder",
})

@dataclass(frozen=True)
class ProductionMetadataRequirement:
    """Immutable production contract selected only by canonical method ID."""

    backend_id: str
    uses_graph: bool
    uses_temporal_filter: bool
    uses_reranker: bool
    uses_verification: bool
    expected_model_name: str | None
    expected_model_revision: str | None
    requires_model_revision: bool
    contract_versions: tuple[str, ...]


PRODUCTION_METADATA_REQUIREMENTS: Mapping[str, ProductionMetadataRequirement] = MappingProxyType({
    "bm25": ProductionMetadataRequirement(
        "rank-bm25", False, True, False, False,
        "bm25-okapi", "0.2.2", True,
        ("rank-bm25==0.2.2", "bm25-tokenizer.v1"),
    ),
    "dense": ProductionMetadataRequirement(
        "sentence-transformers", False, True, False, False,
        "sentence-transformers/all-MiniLM-L6-v2",
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", True,
        ("sentence-transformers>=3.0.0", "all-MiniLM-L6-v2@1110a243"),
    ),
    "static_kg": ProductionMetadataRequirement(
        "temporal-evidence-graph", True, False, False, False,
        None, None, False,
        ("evidence-span.v1", "retrieval-safe-graph.v1"),
    ),
    "temporal_kg": ProductionMetadataRequirement(
        "temporal-evidence-graph", True, True, False, False,
        None, None, False,
        ("evidence-span.v1", "retrieval-safe-graph.v1", "valid-source-time.v1"),
    ),
    "temporal_kg_rerank": ProductionMetadataRequirement(
        "cross-encoder", True, True, True, False,
        "BAAI/bge-reranker-base", None, True,
        ("evidence-span.v1", "valid-source-time.v1", "cross-encoder-model-pin.v1"),
    ),
    "temporal_kg_verify": ProductionMetadataRequirement(
        "source-time-verifier", True, True, True, True,
        "deterministic-temporal-verifier", "1.0.0", True,
        ("evidence-span.v1", "valid-source-time.v1", "source-time-verifier==1.0.0"),
    ),
})

PRODUCTION_BACKEND_IDS: Mapping[str, str] = MappingProxyType({
    method_id: requirement.backend_id
    for method_id, requirement in PRODUCTION_METADATA_REQUIREMENTS.items()
})


@dataclass(frozen=True)
class CorpusRecord:
    """Source-derived evidence available to every comparable method."""

    evidence_id: str
    issuer: str
    valid_time: date
    text: str
    numeric_value: CorpusNumericValue = None
    source_time: date | None = None
    schema_version: str = CORPUS_RECORD_SCHEMA_VERSION
    source_schema_version: str | None = None
    document_id: str | None = None
    source_id: str | None = None
    asset_id: str | None = None
    valid_to: date | None = None
    page_id: str | None = None
    block_id: str | None = None
    report_period: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    section: str | None = None
    text_hash: str | None = None
    content_hash: str | None = None
    extraction_confidence: float | None = None
    provider: str | None = None
    structured_values: tuple[tuple[str, CorpusNumericValue], ...] = ()

    @property
    def valid_from(self) -> date:
        return self.valid_time


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
        requirement = PRODUCTION_METADATA_REQUIREMENTS.get(self.method_id)
        if requirement is None:
            raise ValueError(f"unknown registered method_id: {self.method_id}")
        if self.implementation_mode == "fixture" and self.backend_status not in {"fixture", "exploratory"}:
            raise ValueError("fixture metadata requires fixture or exploratory backend status")
        if self.implementation_mode == "production" and self.backend_status not in {
            "production_verified", "production_unavailable"
        }:
            raise ValueError("production metadata requires an explicit production backend status")
        if self.implementation_mode == "production":
            if not isinstance(self.backend, str) or not self.backend.strip():
                raise ValueError(
                    "production metadata requires a non-empty production backend identifier"
                )
            if self.backend.strip().casefold() in NON_PRODUCTION_BACKEND_IDS:
                raise ValueError(
                    "production metadata requires a genuine production backend identifier, "
                    "not fixture, exploratory, or placeholder"
                )
            expected_backend = requirement.backend_id
            if self.backend != expected_backend:
                raise ValueError(
                    f"production metadata requires backend identifier for {self.method_id}: "
                    f"{expected_backend}"
                )

            if requirement.expected_model_name is not None and (
                not isinstance(self.model_name, str) or not self.model_name.strip()
            ):
                raise ValueError("production metadata requires a non-empty model_name")
            if (
                requirement.expected_model_name is not None
                and self.model_name != requirement.expected_model_name
            ):
                raise ValueError(
                    f"production metadata requires model_name for {self.method_id}: "
                    f"{requirement.expected_model_name}"
                )
            if (
                self.backend_status == "production_verified"
                and requirement.requires_model_revision
                and (not isinstance(self.model_revision, str) or not self.model_revision.strip())
            ):
                raise ValueError("production metadata requires an immutable model_revision")
            if (
                requirement.expected_model_revision is not None
                and self.model_revision is not None
                and self.model_revision != requirement.expected_model_revision
            ):
                raise ValueError(
                    f"production metadata requires model_revision for {self.method_id}: "
                    f"{requirement.expected_model_revision}"
                )

            capabilities = (
                self.uses_graph,
                self.uses_temporal_filter,
                self.uses_reranker,
                self.uses_verification,
            )
            expected_capabilities = (
                requirement.uses_graph,
                requirement.uses_temporal_filter,
                requirement.uses_reranker,
                requirement.uses_verification,
            )
            if capabilities != expected_capabilities:
                raise ValueError(
                    f"production capability metadata for {self.method_id} must match "
                    "method-derived requirements"
                )


class Retriever(Protocol):
    method_name: str
    corpus: tuple[CorpusRecord, ...]
    cutoff: date
    corpus_fingerprint: str
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
        records_by_document_id: dict[str, list[CorpusRecord]] = {}
        for record in self.corpus:
            if record.document_id is not None:
                records_by_document_id.setdefault(record.document_id, []).append(record)
        self._corpus_by_document_id = {
            document_id: tuple(sorted(records, key=lambda item: item.evidence_id))
            for document_id, records in records_by_document_id.items()
        }
        self.metadata.validate()

    def retrieve(self, question: RetrieverQuery, top_k: int = 5) -> tuple[RetrievalResult, ...]:
        if type(question) is not RetrieverQuery:
            raise TypeError("retrieval accepts only RetrieverQuery")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if question.valid_at != self.cutoff:
            raise ValueError("question cutoff must equal the shared method cutoff")
        self._begin_execution()
        ranked = self._rank_records(self._candidate_records(question), question)
        results = tuple(
            RetrievalResult(self.method_name, question.question_id, record.evidence_id, rank, score,
                            record.valid_time <= question.valid_at, self._verification_status(record, question))
            for rank, (score, record) in enumerate(ranked[:top_k], start=1)
        )
        from .provenance import backend_identity, _record_successful_execution

        if backend_identity(self) is not None and self._execution_proof_complete():
            self.metadata = replace(self.metadata, backend_status="production_verified")
            self.metadata.validate()
            _record_successful_execution(self, query=question, top_k=top_k, outputs=results)
        return results

    def _execution_proof_complete(self) -> bool:
        """Whether this concrete backend completed all required runtime work."""

        return True

    def _begin_execution(self) -> None:
        """Reset per-invocation execution evidence before backend work starts."""

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
        _validate_final_setup(methods, clear_receipts=True)

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
    if final_benchmark:
        validate_final_benchmark(methods, query=query, top_k=top_k, outputs=output)
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


def _validate_final_setup(methods: Sequence[Retriever], *, clear_receipts: bool) -> None:
    """Validate factory, adapter, dependency, and fingerprint state before execution."""

    from .provenance import (
        backend_identity,
        validate_backend_identity,
        _clear_execution_receipt,
    )

    expected_run_id: str | None = None
    expected_adapter_receipt_id: str | None = None
    computed_fingerprints: list[tuple[Retriever, str]] = []
    for method in methods:
        method.metadata.validate()
        if method.metadata.implementation_mode != "production":
            raise ValueError(f"final benchmark rejects fixture-mode method: {method.method_name}")

    for method in methods:
        reported_fingerprint = getattr(method, "corpus_fingerprint", None)
        if reported_fingerprint is None:
            raise ValueError(
                f"final benchmark method {method.method_name} is missing canonical corpus fingerprint"
            )
        validate_fingerprint_value(reported_fingerprint)
        computed_fingerprint = corpus_fingerprint(method.corpus)
        if not hmac.compare_digest(reported_fingerprint, computed_fingerprint):
            raise ValueError(
                f"reported corpus fingerprint does not match canonical corpus for {method.method_name}"
            )
        computed_fingerprints.append((method, computed_fingerprint))

    for method, computed_fingerprint in computed_fingerprints:
        identity = backend_identity(method)
        if identity is None:
            raise ValueError(
                f"final benchmark requires a factory-created backend instance: {method.method_name}"
            )
        if identity.method_id != method.method_name:
            raise ValueError("factory backend identity method does not match registered method")
        if identity.corpus_fingerprint != computed_fingerprint:
            raise ValueError("factory backend identity belongs to another corpus")
        expected_run_id = expected_run_id or identity.run_id
        expected_adapter_receipt_id = expected_adapter_receipt_id or identity.adapter_receipt_id
        validate_backend_identity(
            identity,
            expected_run_id=expected_run_id,
            expected_adapter_receipt_id=expected_adapter_receipt_id,
        )
        if clear_receipts:
            _clear_execution_receipt(method)


def validate_final_benchmark(
    methods: Sequence[Retriever],
    *,
    query: RetrieverQuery | None = None,
    top_k: int = 5,
    outputs: Mapping[str, tuple[RetrievalResult, ...]] | None = None,
) -> None:
    """Require trusted execution evidence before results can be called final."""

    from .provenance import backend_identity, execution_receipt, validate_execution_receipt

    for method in methods:
        if method.metadata.backend_status == "production_unavailable":
            raise ValueError(
                f"final benchmark requires production_verified backend status: {method.method_name}"
            )
    _validate_final_setup(methods, clear_receipts=False)
    run_ids = {backend_identity(method).run_id for method in methods}
    if len(run_ids) != 1:
        raise ValueError("final benchmark requires one shared factory run ID")
    expected_run_id = next(iter(run_ids))
    if (query is None) != (outputs is None):
        raise ValueError("final benchmark receipt validation requires both query and outputs")
    for method in methods:
        if method.metadata.backend_status != "production_verified":
            raise ValueError(
                f"final benchmark requires production_verified backend status: {method.method_name}"
            )
        if query is None or outputs is None:
            if execution_receipt(method) is None:
                raise ValueError(
                    f"final benchmark requires successful execution evidence: {method.method_name}"
                )
            continue
        if method.method_name not in outputs:
            raise ValueError(f"final benchmark output missing method: {method.method_name}")
        validate_execution_receipt(
            method,
            query=query,
            top_k=top_k,
            outputs=outputs[method.method_name],
            expected_run_id=expected_run_id,
        )


def retrieval_manifest(methods: Sequence[Retriever]) -> Mapping[str, RetrievalMetadata]:
    """Metadata retained beside method-keyed comparison outputs."""

    return {method.method_name: method.metadata for method in methods}


def _terms(text: str) -> frozenset[str]:
    return frozenset("".join(character if character.isalnum() else " " for character in text.lower()).split())


def _canonical_decimal(value: Decimal) -> str:
    """Return exact finite Decimal value in plain notation.

    Fractional trailing zeroes are removed, exponent notation is expanded, and
    every signed representation of zero is normalized to ``0``. Non-zero sign
    and every significant decimal digit are preserved without binary-float
    conversion.
    """
    if not value.is_finite():
        raise ValueError("Decimal numeric_value must be finite")
    if value.is_zero():
        return "0"
    plain = format(value, "f")
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return plain


def _canonical_numeric_value(value: CorpusNumericValue) -> dict[str, str]:
    """Encode one numeric field with an explicit, lossless type tag."""
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        raise ValueError("bool numeric_value is not an integer corpus value")
    if type(value) is int:
        return {"type": "integer", "value": str(value)}
    if type(value) is Decimal:
        return {"type": "decimal", "value": _canonical_decimal(value)}
    if type(value) is float:
        if not isfinite(value):
            raise ValueError("binary float numeric_value must be finite")
        return {"type": "binary_float", "value": value.hex()}
    if type(value) is str:
        return {"type": "source_text", "value": value}
    raise ValueError(
        "numeric_value must be a supported built-in Python value; NumPy and unsupported "
        "third-party scalar types are rejected"
    )


def validate_fingerprint_value(value: object) -> str:
    """Return one strictly represented lowercase SHA-256 fingerprint."""

    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("fingerprint must be a built-in lowercase SHA-256 hexadecimal string")
    return value


def canonical_corpus_bytes(corpus: Sequence[CorpusRecord]) -> bytes:
    """Serialize exact retriever-visible corpus identity as canonical JSON.

    Records are sorted by stable evidence identity. Objects use explicit field
    names. Stored text is preserved byte-for-byte through UTF-8 JSON encoding;
    retriever-specific normalization is backend metadata, not corpus identity.
    Dates use ISO 8601 calendar format. Numeric values use tagged exact
    representations: arbitrary-precision integers, normalized exact Decimals,
    exact ``float.hex()`` binary floats, exact source text, or explicit null.

    Returns:
        Canonical compact JSON encoded as UTF-8 bytes.
    """
    identifiers = [record.evidence_id for record in corpus]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("canonical corpus evidence_id values must be unique")

    canonical_records: list[dict[str, object]] = []
    for record in sorted(corpus, key=lambda item: item.evidence_id):
        structured_values = [
            {"name": name, "value": _canonical_numeric_value(value)}
            for name, value in sorted(record.structured_values, key=lambda item: item[0])
        ]
        bbox = None
        if record.bbox is not None:
            bbox = [_canonical_numeric_value(value)["value"] for value in record.bbox]
        canonical_records.append({
            "asset_id": record.asset_id,
            "bbox": bbox,
            "block_id": record.block_id,
            "content_hash": record.content_hash,
            "document_id": record.document_id,
            "evidence_id": record.evidence_id,
            "extraction_confidence": (
                _canonical_numeric_value(record.extraction_confidence)
                if record.extraction_confidence is not None
                else {"type": "null"}
            ),
            "fingerprint_schema_version": CORPUS_FINGERPRINT_SCHEMA_VERSION,
            "issuer_id": record.issuer,
            "numeric_value": _canonical_numeric_value(record.numeric_value),
            "page_id": record.page_id,
            "provider": record.provider,
            "report_period": record.report_period,
            "schema_version": record.schema_version,
            "section": record.section,
            "source_id": record.source_id,
            "source_schema_version": record.source_schema_version,
            "source_time": record.source_time.isoformat() if record.source_time is not None else None,
            "structured_values": structured_values,
            "text": record.text,
            "text_hash": record.text_hash,
            "valid_from": record.valid_from.isoformat(),
            "valid_to": record.valid_to.isoformat() if record.valid_to is not None else None,
        })

    return json.dumps(
        canonical_records,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def corpus_fingerprint(corpus: Sequence[CorpusRecord]) -> str:
    """Return SHA-256 over the canonical retriever-visible corpus bytes."""
    return hashlib.sha256(canonical_corpus_bytes(corpus)).hexdigest()


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

    from .production_factory import production_retrievers

    return production_retrievers(corpus, cutoff=cutoff, graph=graph)  # type: ignore[arg-type]
