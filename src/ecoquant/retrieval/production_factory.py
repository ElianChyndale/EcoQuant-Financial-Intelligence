"""Approved construction boundary for trusted production retrievers."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from uuid import uuid4

from ecoquant.evidence_graph.graph import TemporalEvidenceGraph

from .base import Retriever, corpus_fingerprint
from .corpus_adapter import AuthoritativeCorpus, _authoritative_corpus_receipt
from .provenance import (
    BackendDependency,
    BackendInstanceIdentity,
    _REGISTRY_SEAL,
    _register_backend_instance,
)


def production_retrievers(
    corpus: AuthoritativeCorpus,
    *,
    cutoff: date,
    graph: TemporalEvidenceGraph | None,
) -> tuple[Retriever, ...]:
    """Construct and register the exact six trusted production methods."""

    adapter_receipt_id, records = _authoritative_corpus_receipt(corpus)
    if not isinstance(graph, TemporalEvidenceGraph):
        raise ValueError("production retrieval requires a TemporalEvidenceGraph")

    from .bm25 import BM25Retriever
    from .dense import DENSE_MODEL, DenseRetriever
    from .kg import StaticKGRetriever, TemporalKGRetriever
    from . import reranker as reranker_module
    from .reranker import TemporalKGRerankRetriever
    from .verifier import TemporalKGVerifyRetriever

    reranker_pin = reranker_module.RERANKER_MODEL
    methods: tuple[Retriever, ...] = (
        BM25Retriever(records, cutoff=cutoff),
        DenseRetriever(records, cutoff=cutoff),
        StaticKGRetriever(records, cutoff=cutoff, graph=graph),
        TemporalKGRetriever(records, cutoff=cutoff, graph=graph),
        TemporalKGRerankRetriever(records, cutoff=cutoff, graph=graph),
        TemporalKGVerifyRetriever(records, cutoff=cutoff, graph=graph),
    )
    methods[4].metadata = replace(methods[4].metadata, model_revision=reranker_pin.revision)

    package_versions = {
        "rank-bm25": _installed_version("rank-bm25"),
        "sentence-transformers": _installed_version("sentence-transformers"),
    }
    run_id = uuid4().hex
    fingerprint = corpus_fingerprint(records)
    dependency_sets = _dependency_sets(
        dense_model_name=DENSE_MODEL.name,
        dense_model_revision=DENSE_MODEL.revision,
        reranker_model_name=reranker_pin.name,
        reranker_model_revision=reranker_pin.revision,
        package_versions=package_versions,
    )
    for method in methods:
        identity = BackendInstanceIdentity(
            method_id=method.method_name,
            backend_type=f"{type(method).__module__}.{type(method).__qualname__}",
            instance_id=uuid4().hex,
            run_id=run_id,
            adapter_receipt_id=adapter_receipt_id,
            corpus_fingerprint=fingerprint,
            dependencies=dependency_sets[method.method_name],
        )
        _register_backend_instance(method, identity, _seal=_REGISTRY_SEAL)
    return methods


def _dependency_sets(
    *,
    dense_model_name: str,
    dense_model_revision: str | None,
    reranker_model_name: str,
    reranker_model_revision: str | None,
    package_versions: dict[str, str],
) -> dict[str, tuple[BackendDependency, ...]]:
    graph = (
        BackendDependency("graph_backend", "temporal-evidence-graph", "1.0.0"),
        BackendDependency("graph_schema", "retrieval-safe-graph.v1", "1"),
    )
    temporal = (*graph, BackendDependency("temporal_contract", "valid-source-time.v1", "1"))
    reranker = (
        *temporal,
        BackendDependency(
            "reranker_backend",
            "cross-encoder",
            package_versions["sentence-transformers"],
        ),
        BackendDependency(
            "reranker_model",
            "sentence-transformers-model",
            "1",
            model_id=reranker_model_name,
            revision=reranker_model_revision,
        ),
    )
    return {
        "bm25": (
            BackendDependency(
                "lexical_backend", "rank-bm25", package_versions["rank-bm25"]
            ),
            BackendDependency("tokenizer", "bm25-tokenizer.v1", "1"),
        ),
        "dense": (
            BackendDependency(
                "dense_backend",
                "sentence-transformers",
                package_versions["sentence-transformers"],
            ),
            BackendDependency(
                "dense_model",
                "sentence-transformers-model",
                "1",
                model_id=dense_model_name,
                revision=dense_model_revision,
            ),
        ),
        "static_kg": graph,
        "temporal_kg": temporal,
        "temporal_kg_rerank": reranker,
        "temporal_kg_verify": (
            *reranker,
            BackendDependency("verifier", "source-time-verifier", "1.0.0"),
        ),
    }


def _installed_version(distribution: str) -> str:
    try:
        installed = version(distribution)
    except PackageNotFoundError as error:
        raise RuntimeError(f"required production package is not installed: {distribution}") from error
    if not installed:
        raise RuntimeError(f"required production package has no version identity: {distribution}")
    return installed
