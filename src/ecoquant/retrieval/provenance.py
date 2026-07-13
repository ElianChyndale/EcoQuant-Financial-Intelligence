"""Trusted production-backend identities and run-scoped execution receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from weakref import WeakKeyDictionary

from .base import RetrievalResult, RetrieverQuery, validate_fingerprint_value


@dataclass(frozen=True)
class BackendDependency:
    role: str
    implementation_id: str
    version: str
    model_id: str | None = None
    revision: str | None = None


@dataclass(frozen=True)
class BackendInstanceIdentity:
    method_id: str
    backend_type: str
    instance_id: str
    run_id: str
    adapter_receipt_id: str
    corpus_fingerprint: str
    dependencies: tuple[BackendDependency, ...]


@dataclass(frozen=True)
class ExecutionReceipt:
    method_id: str
    instance_id: str
    run_id: str
    corpus_fingerprint: str
    query_digest: str
    valid_at: date
    source_cutoff: date
    top_k: int
    dependency_digest: str
    output_digest: str
    status: str


@dataclass(frozen=True)
class _DependencyRequirement:
    implementation_id: str
    version: str | None = None
    model_id: str | None = None
    revision: str | None = None
    requires_revision: bool = False


_BACKEND_TYPES = MappingProxyType({
    "bm25": "ecoquant.retrieval.bm25.BM25Retriever",
    "dense": "ecoquant.retrieval.dense.DenseRetriever",
    "static_kg": "ecoquant.retrieval.kg.StaticKGRetriever",
    "temporal_kg": "ecoquant.retrieval.kg.TemporalKGRetriever",
    "temporal_kg_rerank": "ecoquant.retrieval.reranker.TemporalKGRerankRetriever",
    "temporal_kg_verify": "ecoquant.retrieval.verifier.TemporalKGVerifyRetriever",
})

_COMMON_GRAPH = {
    "graph_backend": _DependencyRequirement("temporal-evidence-graph", version="1.0.0"),
    "graph_schema": _DependencyRequirement("retrieval-safe-graph.v1", version="1"),
}
_TEMPORAL = {
    **_COMMON_GRAPH,
    "temporal_contract": _DependencyRequirement("valid-source-time.v1", version="1"),
}
_RERANK = {
    **_TEMPORAL,
    "reranker_backend": _DependencyRequirement("cross-encoder"),
    "reranker_model": _DependencyRequirement(
        "sentence-transformers-model",
        model_id="BAAI/bge-reranker-base",
        requires_revision=True,
    ),
}
_DEPENDENCY_REQUIREMENTS = MappingProxyType({
    "bm25": MappingProxyType({
        "lexical_backend": _DependencyRequirement("rank-bm25"),
        "tokenizer": _DependencyRequirement("bm25-tokenizer.v1", version="1"),
    }),
    "dense": MappingProxyType({
        "dense_backend": _DependencyRequirement("sentence-transformers"),
        "dense_model": _DependencyRequirement(
            "sentence-transformers-model",
            model_id="sentence-transformers/all-MiniLM-L6-v2",
            revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
            requires_revision=True,
        ),
    }),
    "static_kg": MappingProxyType(dict(_COMMON_GRAPH)),
    "temporal_kg": MappingProxyType(dict(_TEMPORAL)),
    "temporal_kg_rerank": MappingProxyType(dict(_RERANK)),
    "temporal_kg_verify": MappingProxyType({
        **_RERANK,
        "verifier": _DependencyRequirement("source-time-verifier", version="1.0.0"),
    }),
})

_REGISTRY_SEAL = object()
_BACKEND_IDENTITIES: WeakKeyDictionary[object, BackendInstanceIdentity] = WeakKeyDictionary()
_EXECUTION_RECEIPTS: WeakKeyDictionary[object, ExecutionReceipt] = WeakKeyDictionary()


def backend_identity(retriever: object) -> BackendInstanceIdentity | None:
    """Return factory-issued identity, never caller attributes."""

    try:
        return _BACKEND_IDENTITIES.get(retriever)
    except TypeError:
        return None


def execution_receipt(retriever: object) -> ExecutionReceipt | None:
    """Return the internally registered latest successful execution receipt."""

    try:
        return _EXECUTION_RECEIPTS.get(retriever)
    except TypeError:
        return None


def validate_backend_identity(
    identity: BackendInstanceIdentity,
    *,
    expected_run_id: str | None = None,
    expected_adapter_receipt_id: str | None = None,
) -> None:
    """Validate a complete method-derived backend dependency chain."""

    if type(identity) is not BackendInstanceIdentity:
        raise ValueError("backend identity must be a factory-issued immutable identity")
    expected_type = _BACKEND_TYPES.get(identity.method_id)
    if expected_type is None:
        raise ValueError(f"unknown backend identity method: {identity.method_id}")
    if identity.backend_type != expected_type:
        raise ValueError(f"backend type mismatch for {identity.method_id}")
    if type(identity.instance_id) is not str or not identity.instance_id:
        raise ValueError("backend identity requires an instance ID")
    if type(identity.run_id) is not str or not identity.run_id:
        raise ValueError("backend identity requires a run ID")
    if expected_run_id is not None and identity.run_id != expected_run_id:
        raise ValueError("backend identity run ID does not match the factory run ID")
    if type(identity.adapter_receipt_id) is not str or not identity.adapter_receipt_id:
        raise ValueError("backend identity requires authoritative adapter provenance")
    if (
        expected_adapter_receipt_id is not None
        and identity.adapter_receipt_id != expected_adapter_receipt_id
    ):
        raise ValueError("backend identity adapter receipt does not match the shared corpus")
    validate_fingerprint_value(identity.corpus_fingerprint)

    requirements = _DEPENDENCY_REQUIREMENTS[identity.method_id]
    dependencies = {dependency.role: dependency for dependency in identity.dependencies}
    if len(dependencies) != len(identity.dependencies) or set(dependencies) != set(requirements):
        raise ValueError(
            f"backend dependency roles for {identity.method_id} must be exactly "
            f"{sorted(requirements)}"
        )
    for role, requirement in requirements.items():
        dependency = dependencies[role]
        if type(dependency) is not BackendDependency:
            raise ValueError(f"{role} dependency must be immutable backend provenance")
        if dependency.implementation_id != requirement.implementation_id:
            raise ValueError(f"{role} dependency identity mismatch")
        if type(dependency.version) is not str or not dependency.version:
            raise ValueError(f"{role} dependency requires a version")
        if requirement.version is not None and dependency.version != requirement.version:
            raise ValueError(f"{role} dependency version mismatch")
        if dependency.model_id != requirement.model_id:
            raise ValueError(f"{role} dependency model identity mismatch")
        if requirement.requires_revision and (
            type(dependency.revision) is not str or not dependency.revision
        ):
            raise ValueError(f"{role} dependency requires an immutable revision")
        if requirement.revision is not None and dependency.revision != requirement.revision:
            raise ValueError(f"{role} dependency revision mismatch")


def validate_execution_receipt(
    retriever: object,
    *,
    query: RetrieverQuery,
    top_k: int,
    outputs: tuple[RetrievalResult, ...],
    expected_run_id: str,
) -> None:
    """Validate the registry receipt against the exact final invocation."""

    identity = backend_identity(retriever)
    if identity is None:
        raise ValueError("final benchmark requires a factory-created backend instance")
    receipt = execution_receipt(retriever)
    if type(receipt) is not ExecutionReceipt:
        raise ValueError(f"final benchmark requires successful execution evidence: {identity.method_id}")
    expected = _build_receipt(identity, query=query, top_k=top_k, outputs=outputs)
    if receipt.method_id != expected.method_id:
        raise ValueError("execution receipt method does not match backend identity")
    if receipt.instance_id != expected.instance_id:
        raise ValueError("execution receipt belongs to another backend instance")
    if receipt.run_id != expected_run_id or receipt.run_id != expected.run_id:
        raise ValueError("execution receipt run ID does not match the final run")
    if receipt.corpus_fingerprint != expected.corpus_fingerprint:
        raise ValueError("execution receipt belongs to another corpus")
    if receipt.query_digest != expected.query_digest:
        raise ValueError("execution receipt belongs to another query")
    if receipt.valid_at != expected.valid_at or receipt.source_cutoff != expected.source_cutoff:
        raise ValueError("execution receipt cutoff identity does not match the query")
    if receipt.top_k != expected.top_k:
        raise ValueError("execution receipt top_k does not match the final boundary")
    if receipt.dependency_digest != expected.dependency_digest:
        raise ValueError("execution receipt dependency identity mismatch")
    if receipt.output_digest != expected.output_digest:
        raise ValueError("execution receipt output identity mismatch")
    if receipt.status != "success":
        raise ValueError("execution receipt does not record successful execution")


def _register_backend_instance(
    retriever: object,
    identity: BackendInstanceIdentity,
    *,
    _seal: object,
) -> None:
    if _seal is not _REGISTRY_SEAL:
        raise ValueError("backend instances may only be registered by the production factory")
    validate_backend_identity(identity)
    expected_type = f"{type(retriever).__module__}.{type(retriever).__qualname__}"
    if identity.backend_type != expected_type:
        raise ValueError("registered backend object does not match its concrete backend identity")
    _BACKEND_IDENTITIES[retriever] = identity


def _clear_execution_receipt(retriever: object) -> None:
    try:
        _EXECUTION_RECEIPTS.pop(retriever, None)
    except TypeError:
        pass


def _record_successful_execution(
    retriever: object,
    *,
    query: RetrieverQuery,
    top_k: int,
    outputs: tuple[RetrievalResult, ...],
) -> None:
    identity = backend_identity(retriever)
    if identity is None:
        return
    _EXECUTION_RECEIPTS[retriever] = _build_receipt(
        identity,
        query=query,
        top_k=top_k,
        outputs=outputs,
    )


def _build_receipt(
    identity: BackendInstanceIdentity,
    *,
    query: RetrieverQuery,
    top_k: int,
    outputs: tuple[RetrievalResult, ...],
) -> ExecutionReceipt:
    return ExecutionReceipt(
        method_id=identity.method_id,
        instance_id=identity.instance_id,
        run_id=identity.run_id,
        corpus_fingerprint=identity.corpus_fingerprint,
        query_digest=_query_digest(query),
        valid_at=query.valid_at,
        source_cutoff=query.effective_source_cutoff,
        top_k=top_k,
        dependency_digest=_dependency_digest(identity.dependencies),
        output_digest=_output_digest(outputs),
        status="success",
    )


def _query_digest(query: RetrieverQuery) -> str:
    return _sha256_json({
        "question_id": query.question_id,
        "issuer_id": query.issuer,
        "query": query.query,
        "source_cutoff": query.effective_source_cutoff.isoformat(),
        "valid_at": query.valid_at.isoformat(),
    })


def _dependency_digest(dependencies: tuple[BackendDependency, ...]) -> str:
    return _sha256_json([
        {
            "implementation_id": dependency.implementation_id,
            "model_id": dependency.model_id,
            "revision": dependency.revision,
            "role": dependency.role,
            "version": dependency.version,
        }
        for dependency in sorted(dependencies, key=lambda item: item.role)
    ])


def _output_digest(outputs: tuple[RetrievalResult, ...]) -> str:
    return _sha256_json([
        {
            "evidence_id": result.evidence_id,
            "method": result.method,
            "question_id": result.question_id,
            "rank": result.rank,
            "score": result.score.hex(),
            "valid_time_match": result.valid_time_match,
            "verification_status": result.verification_status,
        }
        for result in outputs
    ])


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
