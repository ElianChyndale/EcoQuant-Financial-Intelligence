from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from ecoquant.document_intelligence.schema import EvidenceSpanV1
from ecoquant.evidence_graph.builder import build_graph
from ecoquant.retrieval.base import (
    PRODUCTION_METADATA_REQUIREMENTS,
    CorpusRecord,
    RetrievalMetadata,
    RetrieverQuery,
    compare_retrievers,
    corpus_fingerprint,
    validate_final_benchmark,
)
from ecoquant.retrieval.corpus_adapter import adapt_evidence_spans
from ecoquant.retrieval.production_factory import production_retrievers
from ecoquant.retrieval.provenance import (
    BackendInstanceIdentity,
    ExecutionReceipt,
    backend_identity,
    execution_receipt,
    validate_backend_identity,
)


def _span(
    *,
    document_id: str = "document-1",
    content_hash: str = "d" * 64,
    text: str = "AIB assets 100",
) -> EvidenceSpanV1:
    return EvidenceSpanV1(
        "evidence-span.v1",
        document_id,
        "AIB",
        "2023",
        date(2024, 3, 1),
        "1",
        "block-1",
        (0.0, 0.0, 10.0, 10.0),
        "Assets",
        text,
        hashlib.sha256(text.encode("utf-8")).hexdigest(),
        1.0,
        "pdf-manager",
        content_hash,
    )


def _query(*, question_id: str = "q1", text: str = "AIB assets") -> RetrieverQuery:
    return RetrieverQuery(
        question_id,
        "AIB",
        text,
        date(2024, 12, 31),
        date(2024, 12, 31),
    )


@pytest.fixture
def executed_factory_run(monkeypatch: pytest.MonkeyPatch):
    import sentence_transformers
    from ecoquant.retrieval import reranker as reranker_module
    from ecoquant.retrieval.dense import ModelPin

    def fake_dense_init(self, *args, **kwargs):
        self.model_name = args[0]

    def fake_dense_encode(self, texts, **kwargs):
        return np.asarray([[float(index + 1), 1.0] for index, _ in enumerate(texts)])

    def fake_cross_init(self, *args, **kwargs):
        self.model_name = args[0]

    def fake_cross_predict(self, pairs):
        return np.asarray([0.75 for _ in pairs])

    monkeypatch.setattr(sentence_transformers.SentenceTransformer, "__init__", fake_dense_init)
    monkeypatch.setattr(sentence_transformers.SentenceTransformer, "encode", fake_dense_encode)
    monkeypatch.setattr(sentence_transformers.CrossEncoder, "__init__", fake_cross_init)
    monkeypatch.setattr(sentence_transformers.CrossEncoder, "predict", fake_cross_predict)
    monkeypatch.setattr(
        reranker_module,
        "RERANKER_MODEL",
        ModelPin("BAAI/bge-reranker-base", "verified-reranker-revision"),
    )

    span = _span()
    corpus = adapt_evidence_spans((span,))
    methods = production_retrievers(
        corpus,
        cutoff=date(2024, 12, 31),
        graph=build_graph((span,)),
    )
    query = _query()
    outputs = compare_retrievers(methods, query, top_k=5, final_benchmark=True)
    return corpus, methods, query, outputs


def _fabricated_metadata(method_id: str) -> RetrievalMetadata:
    requirement = PRODUCTION_METADATA_REQUIREMENTS[method_id]
    revision = requirement.expected_model_revision
    if requirement.requires_model_revision and revision is None:
        revision = "caller-invented-revision"
    return RetrievalMetadata(
        method_id,
        "production",
        requirement.backend_id,
        requirement.expected_model_name,
        revision,
        requirement.uses_graph,
        requirement.uses_temporal_filter,
        requirement.uses_reranker,
        requirement.uses_verification,
        backend_status="production_verified",
    )


class _FabricatedRetriever:
    def __init__(self, method_id: str, corpus: tuple[CorpusRecord, ...], cutoff: date) -> None:
        self.method_name = method_id
        self.corpus = corpus
        self.cutoff = cutoff
        self.corpus_fingerprint = corpus_fingerprint(corpus)
        self.metadata = _fabricated_metadata(method_id)
        self.successful_execution = True

    def retrieve(self, question: RetrieverQuery, *, top_k: int = 5):
        return ()


def test_production_factory_rejects_handcrafted_corpus() -> None:
    handcrafted = (CorpusRecord("e", "AIB", date(2023, 12, 31), "AIB assets"),)

    with pytest.raises(ValueError, match="adapter-produced AuthoritativeCorpus"):
        production_retrievers(handcrafted, cutoff=date(2024, 12, 31), graph=build_graph(()))


def test_six_fabricated_retrievers_and_metadata_cannot_pass_final_mode() -> None:
    corpus = (CorpusRecord("e", "AIB", date(2023, 12, 31), "AIB assets"),)
    methods = tuple(
        _FabricatedRetriever(method_id, corpus, date(2024, 12, 31))
        for method_id in PRODUCTION_METADATA_REQUIREMENTS
    )

    with pytest.raises(ValueError, match="factory-created backend instance"):
        compare_retrievers(methods, _query(), top_k=5, final_benchmark=True)


def test_copied_metadata_and_receipt_shaped_attribute_are_not_proof(executed_factory_run) -> None:
    corpus, methods, query, _ = executed_factory_run
    fake = _FabricatedRetriever("dense", corpus.records, query.valid_at)
    fake.metadata = methods[1].metadata
    fake.execution_receipt = execution_receipt(methods[1])

    assert backend_identity(fake) is None
    assert execution_receipt(fake) is None


def test_factory_identity_is_run_scoped_complete_and_unique(executed_factory_run) -> None:
    corpus, methods, _, _ = executed_factory_run
    identities = [backend_identity(method) for method in methods]

    assert all(type(identity) is BackendInstanceIdentity for identity in identities)
    assert len({identity.instance_id for identity in identities}) == 6
    assert len({identity.run_id for identity in identities}) == 1
    assert {identity.corpus_fingerprint for identity in identities} == {
        corpus_fingerprint(corpus.records)
    }
    assert [identity.method_id for identity in identities] == [method.method_name for method in methods]


@pytest.mark.parametrize(
    ("method_id", "expected_roles"),
    (
        ("bm25", {"lexical_backend", "tokenizer"}),
        ("dense", {"dense_backend", "dense_model"}),
        ("static_kg", {"graph_backend", "graph_schema"}),
        ("temporal_kg", {"graph_backend", "graph_schema", "temporal_contract"}),
        (
            "temporal_kg_rerank",
            {"graph_backend", "graph_schema", "temporal_contract", "reranker_backend", "reranker_model"},
        ),
        (
            "temporal_kg_verify",
            {
                "graph_backend", "graph_schema", "temporal_contract", "reranker_backend",
                "reranker_model", "verifier",
            },
        ),
    ),
)
def test_every_method_identity_contains_exact_dependency_roles(
    executed_factory_run, method_id: str, expected_roles: set[str]
) -> None:
    _, methods, _, _ = executed_factory_run
    method = next(method for method in methods if method.method_name == method_id)
    identity = backend_identity(method)

    assert {dependency.role for dependency in identity.dependencies} == expected_roles
    validate_backend_identity(identity)


@pytest.mark.parametrize(
    ("method_id", "missing_role"),
    (
        ("temporal_kg_rerank", "graph_backend"),
        ("temporal_kg_rerank", "graph_schema"),
        ("temporal_kg_rerank", "reranker_model"),
        ("temporal_kg_verify", "graph_backend"),
        ("temporal_kg_verify", "reranker_model"),
        ("temporal_kg_verify", "verifier"),
    ),
)
def test_composite_identity_rejects_missing_inherited_dependency(
    executed_factory_run, method_id: str, missing_role: str
) -> None:
    _, methods, _, _ = executed_factory_run
    identity = backend_identity(next(method for method in methods if method.method_name == method_id))
    incomplete = replace(
        identity,
        dependencies=tuple(dep for dep in identity.dependencies if dep.role != missing_role),
    )

    with pytest.raises(ValueError, match="dependency roles"):
        validate_backend_identity(incomplete)


def test_composite_identity_rejects_missing_reranker_revision(executed_factory_run) -> None:
    _, methods, _, _ = executed_factory_run
    identity = backend_identity(methods[4])
    dependencies = tuple(
        replace(dep, revision=None) if dep.role == "reranker_model" else dep
        for dep in identity.dependencies
    )

    with pytest.raises(ValueError, match="immutable revision"):
        validate_backend_identity(replace(identity, dependencies=dependencies))


def test_composite_identity_rejects_missing_reranker_model_id(executed_factory_run) -> None:
    _, methods, _, _ = executed_factory_run
    identity = backend_identity(methods[4])
    dependencies = tuple(
        replace(dep, model_id=None) if dep.role == "reranker_model" else dep
        for dep in identity.dependencies
    )

    with pytest.raises(ValueError, match="model identity"):
        validate_backend_identity(replace(identity, dependencies=dependencies))


def test_verify_identity_rejects_missing_verifier_version(executed_factory_run) -> None:
    _, methods, _, _ = executed_factory_run
    identity = backend_identity(methods[5])
    dependencies = tuple(
        replace(dep, version="") if dep.role == "verifier" else dep
        for dep in identity.dependencies
    )

    with pytest.raises(ValueError, match="verifier.*version"):
        validate_backend_identity(replace(identity, dependencies=dependencies))


def test_composite_identity_rejects_dependency_identity_mismatch(executed_factory_run) -> None:
    _, methods, _, _ = executed_factory_run
    identity = backend_identity(methods[4])
    dependencies = tuple(
        replace(dep, implementation_id="wrong-graph") if dep.role == "graph_backend" else dep
        for dep in identity.dependencies
    )

    with pytest.raises(ValueError, match="graph_backend"):
        validate_backend_identity(replace(identity, dependencies=dependencies))


def test_constructor_only_models_have_no_receipts_or_verified_status(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentence_transformers
    from ecoquant.retrieval import reranker as reranker_module
    from ecoquant.retrieval.dense import ModelPin

    monkeypatch.setattr(sentence_transformers.CrossEncoder, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(
        reranker_module,
        "RERANKER_MODEL",
        ModelPin("BAAI/bge-reranker-base", "verified-reranker-revision"),
    )
    span = _span()
    corpus = adapt_evidence_spans((span,))
    from ecoquant.retrieval.reranker import TemporalKGRerankRetriever

    method = TemporalKGRerankRetriever(
        corpus.records,
        cutoff=date(2024, 12, 31),
        graph=build_graph((span,)),
    )

    assert method.metadata.backend_status == "production_unavailable"
    assert execution_receipt(method) is None


def test_constructor_only_bm25_and_graph_backends_are_not_verified() -> None:
    from ecoquant.retrieval.bm25 import BM25Retriever
    from ecoquant.retrieval.kg import StaticKGRetriever, TemporalKGRetriever

    span = _span()
    corpus = adapt_evidence_spans((span,))
    graph = build_graph((span,))
    methods = (
        BM25Retriever(corpus.records, cutoff=date(2024, 12, 31)),
        StaticKGRetriever(corpus.records, cutoff=date(2024, 12, 31), graph=graph),
        TemporalKGRetriever(corpus.records, cutoff=date(2024, 12, 31), graph=graph),
    )

    assert all(method.metadata.backend_status == "production_unavailable" for method in methods)
    assert all(execution_receipt(method) is None for method in methods)


def test_partial_dense_model_load_produces_no_execution_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentence_transformers
    from ecoquant.retrieval.dense import DenseRetriever

    monkeypatch.setattr(sentence_transformers.SentenceTransformer, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(
        sentence_transformers.SentenceTransformer,
        "encode",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(OSError("partial weights")),
    )

    with pytest.raises(RuntimeError, match="partial weights"):
        DenseRetriever(
            (CorpusRecord("e", "AIB", date(2023, 12, 31), "AIB assets"),),
            cutoff=date(2024, 12, 31),
        )


def test_successful_final_execution_issues_matching_receipts(executed_factory_run) -> None:
    corpus, methods, query, outputs = executed_factory_run

    validate_final_benchmark(methods, query=query, top_k=5, outputs=outputs)
    for method in methods:
        receipt = execution_receipt(method)
        identity = backend_identity(method)
        assert type(receipt) is ExecutionReceipt
        assert receipt.method_id == method.method_name
        assert receipt.instance_id == identity.instance_id
        assert receipt.run_id == identity.run_id
        assert receipt.corpus_fingerprint == corpus_fingerprint(corpus.records)
        assert receipt.valid_at == query.valid_at
        assert receipt.source_cutoff == query.source_cutoff
        assert receipt.top_k == 5
        assert receipt.status == "success"
        assert method.metadata.backend_status == "production_verified"


@pytest.mark.parametrize(
    "results",
    (
        (
            ("a", 1, 1.0),
            ("b", 1, 0.5),
        ),
        (
            ("b", 1, 1.0),
            ("a", 2, 1.0),
        ),
    ),
)
def test_trusted_final_backend_rejects_noncanonical_ranks(executed_factory_run, results) -> None:
    _, methods, query, _ = executed_factory_run
    from ecoquant.retrieval.base import RetrievalResult

    methods[0].retrieve = lambda question, top_k=5: tuple(
        RetrievalResult("bm25", question.question_id, evidence_id, rank, score, True, "unverified")
        for evidence_id, rank, score in results
    )

    with pytest.raises(ValueError, match="canonical ranks and score ordering"):
        compare_retrievers(methods, query, top_k=5, final_benchmark=True)


@pytest.mark.parametrize("score", (float("nan"), float("inf"), float("-inf")))
def test_trusted_final_backend_rejects_nonfinite_scores(executed_factory_run, score: float) -> None:
    _, methods, query, _ = executed_factory_run
    from ecoquant.retrieval.base import RetrievalResult

    methods[0].retrieve = lambda question, top_k=5: (
        RetrievalResult("bm25", question.question_id, "bad", 1, score, True, "unverified"),
    )

    with pytest.raises(ValueError, match="finite"):
        compare_retrievers(methods, query, top_k=5, final_benchmark=True)


def test_trusted_final_backend_rejects_relabelled_unavailable_status(executed_factory_run) -> None:
    _, methods, query, outputs = executed_factory_run
    methods[1].metadata = replace(methods[1].metadata, backend_status="production_unavailable")

    with pytest.raises(ValueError, match="production_verified"):
        validate_final_benchmark(methods, query=query, top_k=5, outputs=outputs)


def test_receipt_from_another_query_is_rejected(executed_factory_run) -> None:
    _, methods, _, outputs = executed_factory_run

    with pytest.raises(ValueError, match="query"):
        validate_final_benchmark(
            methods,
            query=_query(question_id="q2", text="different query"),
            top_k=5,
            outputs=outputs,
        )


def test_prior_model_success_cannot_authorize_later_empty_execution(executed_factory_run) -> None:
    _, methods, _, _ = executed_factory_run
    empty_query = RetrieverQuery(
        "q-empty",
        "UNKNOWN",
        "no candidates",
        date(2024, 12, 31),
        date(2024, 12, 31),
    )

    with pytest.raises(ValueError, match="successful execution evidence: dense"):
        compare_retrievers(methods, empty_query, top_k=5, final_benchmark=True)


def test_receipt_from_another_corpus_or_run_is_rejected(executed_factory_run) -> None:
    _, methods, query, outputs = executed_factory_run
    first_identity = backend_identity(methods[0])
    inconsistent = replace(first_identity, run_id="another-run")

    with pytest.raises(ValueError, match="run ID"):
        validate_backend_identity(inconsistent, expected_run_id=backend_identity(methods[1]).run_id)


def test_factory_identity_from_another_corpus_is_rejected(executed_factory_run) -> None:
    _, methods, query, _ = executed_factory_run
    changed = tuple(replace(record, text=record.text + " changed") for record in methods[0].corpus)
    changed_fingerprint = corpus_fingerprint(changed)
    for method in methods:
        method.corpus = changed
        method.corpus_fingerprint = changed_fingerprint

    with pytest.raises(ValueError, match="identity belongs to another corpus"):
        compare_retrievers(methods, query, top_k=5, final_benchmark=True)


@pytest.mark.parametrize("method_index", range(6))
def test_every_final_method_strictly_validates_its_fingerprint(executed_factory_run, method_index: int) -> None:
    _, methods, query, _ = executed_factory_run
    methods[method_index].corpus_fingerprint = type(
        "EqualToAnything",
        (),
        {"__eq__": lambda self, other: True, "__bool__": lambda self: True},
    )()

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        compare_retrievers(methods, query, top_k=5, final_benchmark=True)


def test_caller_created_receipt_value_is_not_registered_proof() -> None:
    fake = object()
    receipt = ExecutionReceipt(
        "dense",
        "instance",
        "run",
        "a" * 64,
        "b" * 64,
        date(2024, 12, 31),
        date(2024, 12, 31),
        5,
        "c" * 64,
        "d" * 64,
        "success",
    )
    setattr_holder = type("Holder", (), {})()
    setattr_holder.execution_receipt = receipt

    assert execution_receipt(fake) is None
    assert execution_receipt(setattr_holder) is None
