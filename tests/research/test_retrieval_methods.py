from __future__ import annotations

from datetime import date
from dataclasses import fields, replace
from inspect import signature

import pytest

from ecoquant.retrieval.base import (
    PRODUCTION_BACKEND_IDS,
    REGISTERED_METHOD_IDS,
    CorpusRecord,
    Question,
    RetrievalMetadata,
    RetrievalResult,
    all_retrievers,
    compare_retrievers,
    corpus_fingerprint,
    validate_final_benchmark,
    retrieval_manifest,
)
from ecoquant.retrieval.evaluation import (
    EvidenceLocation,
    EvaluationLabels,
    paired_issuer_clustered_bootstrap,
    score_retrieval,
)
from ecoquant.evidence_graph.builder import build_graph
from ecoquant.document_intelligence.schema import EvidenceSpanV1
from ecoquant.evidence_graph.graph import Relation, TemporalEvidenceGraph
from ecoquant.evidence_graph.models import Document, Issuer
from ecoquant.retrieval.kg import StaticKGRetriever


def frozen_corpus() -> tuple[CorpusRecord, ...]:
    return (
        CorpusRecord("aib-2022", "AIB", date(2022, 12, 31), "AIB total assets 129.8 EUR billions", 129.8),
        CorpusRecord("aib-2023", "AIB", date(2023, 12, 31), "AIB total assets 136.3 EUR billions", 136.3),
        CorpusRecord("aib-2024", "AIB", date(2024, 12, 31), "AIB total assets 141.3 EUR billions", 141.3),
        CorpusRecord("esb-2023", "ESB", date(2023, 12, 31), "ESB average employees 8890", 8890),
        CorpusRecord("esb-2024", "ESB", date(2024, 12, 31), "ESB average employees 9588", 9588),
        CorpusRecord("aib-conflict", "AIB", date(2023, 12, 31), "AIB total assets contradiction 130.0", 130.0),
    )


def frozen_question() -> Question:
    return Question(
        question_id="aib-assets-2023",
        issuer="AIB",
        query="What were AIB total assets in 2023?",
        cutoff=date(2023, 12, 31),
        source_cutoff=date(2023, 12, 31),
    )


def source_graph(records: tuple[CorpusRecord, ...]) -> TemporalEvidenceGraph:
    """Create a source-derived retrieval graph for the fixture corpus."""
    graph = TemporalEvidenceGraph()
    issuers: set[str] = set()
    for record in records:
        if record.issuer not in issuers:
            graph.add_node(Issuer(record.issuer, record.valid_time, record.source_time or record.valid_time, record.issuer))
            issuers.add(record.issuer)
        graph.add_node(Document(record.evidence_id, record.valid_time, record.source_time or record.valid_time, record.issuer))
        graph.add_edge(record.issuer, record.evidence_id, Relation.CONTAINS)
    return graph


def all_methods():
    """Return fixture-mode retrievers for deterministic unit testing."""
    corpus = frozen_corpus()
    return all_retrievers(corpus, cutoff=frozen_question().cutoff, graph=source_graph(corpus), mode="fixture")


@pytest.mark.parametrize("method", all_methods(), ids=lambda item: item.method_name)
def test_every_retriever_returns_ranked_top_five(method) -> None:
    results = method.retrieve(frozen_question(), top_k=5)

    assert 1 <= len(results) <= 5
    assert [result.rank for result in results] == list(range(1, len(results) + 1))
    assert all(results[index].score >= results[index + 1].score for index in range(len(results) - 1))
    assert all(result.question_id == "aib-assets-2023" for result in results)


def test_all_methods_share_the_exact_frozen_corpus_and_cutoff() -> None:
    methods = all_methods()

    assert {method.corpus for method in methods} == {frozen_corpus()}
    assert {method.cutoff for method in methods} == {date(2023, 12, 31)}
    assert {method.method_name for method in methods} == {
        "bm25", "dense", "static_kg", "temporal_kg", "temporal_kg_rerank", "temporal_kg_verify"
    }


def test_comparable_retrieval_enforces_the_shared_top_five_cutoff() -> None:
    with pytest.raises(ValueError, match="top_k must be positive"):
        compare_retrievers(all_methods(), frozen_question(), top_k=0)


class _HostileRetriever:
    def __init__(self, method_name: str, results: tuple[RetrievalResult, ...]) -> None:
        self.method_name = method_name
        self.results = results
        self.received_top_k: int | None = None
        self.metadata = RetrievalMetadata.fixture(method_name)

    def retrieve(self, question: Question, top_k: int = 5) -> tuple[RetrievalResult, ...]:
        self.received_top_k = top_k
        return self.results


def _hostile_methods() -> tuple[_HostileRetriever, ...]:
    methods: list[_HostileRetriever] = []
    for name in REGISTERED_METHOD_IDS:
        results = tuple(
            RetrievalResult(name, "aib-assets-2023", f"{name}-{index:02}", 99 - index, 1.0 if index < 2 else 0.5, True, "unverified")
            for index in range(12)
        )
        methods.append(_HostileRetriever(name, results))
    return tuple(methods)


class _FinalHostileRetriever(_HostileRetriever):
    def __init__(
        self,
        method_name: str,
        corpus: tuple[CorpusRecord, ...],
        *,
        fingerprint: str | None = None,
    ) -> None:
        super().__init__(method_name, ())
        self.corpus = corpus
        self.cutoff = frozen_question().cutoff
        self.corpus_fingerprint = fingerprint if fingerprint is not None else corpus_fingerprint(corpus)
        self.metadata = RetrievalMetadata(
            method_name,
            "production",
            PRODUCTION_BACKEND_IDS.get(method_name, "placeholder"),
            f"test-{method_name}",
            "0123456789abcdef0123456789abcdef01234567",
            "kg" in method_name,
            method_name != "static_kg",
            "rerank" in method_name or "verify" in method_name,
            method_name == "temporal_kg_verify",
            "production_verified",
        )


def _final_hostile_methods(
    corpus: tuple[CorpusRecord, ...] | None = None,
) -> tuple[_FinalHostileRetriever, ...]:
    shared_corpus = corpus or frozen_corpus()
    return tuple(_FinalHostileRetriever(name, shared_corpus) for name in REGISTERED_METHOD_IDS)


def test_final_boundary_rejects_equal_length_different_corpora() -> None:
    methods = list(_final_hostile_methods())
    changed = tuple(
        CorpusRecord(
            record.evidence_id,
            record.issuer,
            record.valid_time,
            "changed evidence" if index == 0 else record.text,
            record.numeric_value,
            record.source_time,
        )
        for index, record in enumerate(frozen_corpus())
    )
    methods[-1] = _FinalHostileRetriever(methods[-1].method_name, changed)

    with pytest.raises(ValueError, match="corpus fingerprint"):
        compare_retrievers(methods, frozen_question(), top_k=5, final_benchmark=True)


def test_final_boundary_rejects_missing_or_unverified_reported_fingerprint() -> None:
    missing = list(_final_hostile_methods())
    del missing[-1].corpus_fingerprint
    with pytest.raises(ValueError, match="missing canonical corpus fingerprint"):
        compare_retrievers(missing, frozen_question(), top_k=5, final_benchmark=True)

    mismatched = list(_final_hostile_methods())
    mismatched[-1].corpus_fingerprint = "0" * 64
    with pytest.raises(ValueError, match="reported corpus fingerprint"):
        compare_retrievers(mismatched, frozen_question(), top_k=5, final_benchmark=True)


def test_final_boundary_rejects_unverified_production_backend_status() -> None:
    methods = list(_final_hostile_methods())
    methods[0].metadata = RetrievalMetadata(
        "bm25",
        "production",
        "rank-bm25",
        "bm25-okapi",
        "0.2.2",
        False,
        True,
        False,
        False,
        backend_status="production_unavailable",
    )

    with pytest.raises(ValueError, match="production_verified"):
        compare_retrievers(methods, frozen_question(), top_k=5, final_benchmark=True)


def test_final_boundary_rejects_fixture_backend_claimed_as_production() -> None:
    methods = list(_final_hostile_methods())
    graph_method = next(method for method in methods if method.method_name == "static_kg")
    graph_method.metadata = replace(graph_method.metadata, backend="fixture")

    with pytest.raises(ValueError, match="production backend identifier"):
        compare_retrievers(methods, frozen_question(), top_k=5, final_benchmark=True)


@pytest.mark.parametrize("top_k", (4, 6))
def test_final_boundary_requires_exactly_five_results(top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k=5"):
        compare_retrievers(_final_hostile_methods(), frozen_question(), top_k=top_k, final_benchmark=True)


def test_final_boundary_requires_explicit_source_cutoff() -> None:
    implicit = Question("q", "AIB", "assets", date(2023, 12, 31))

    with pytest.raises(ValueError, match="explicit source_cutoff"):
        compare_retrievers(_final_hostile_methods(), implicit, top_k=5, final_benchmark=True)


def test_exploratory_comparison_is_explicitly_non_final() -> None:
    compared = compare_retrievers(_hostile_methods(), frozen_question(), top_k=4, final_benchmark=False)

    assert set(compared) == set(REGISTERED_METHOD_IDS)
    assert all(len(results) == 4 for results in compared.values())


def test_final_boundary_rejects_missing_and_extra_methods() -> None:
    methods = _final_hostile_methods()
    with pytest.raises(ValueError, match="exactly the six"):
        compare_retrievers(methods[:-1], frozen_question(), top_k=5, final_benchmark=True)

    extra = _FinalHostileRetriever("extra", frozen_corpus())
    with pytest.raises(ValueError, match="exactly the six|registered"):
        compare_retrievers((*methods, extra), frozen_question(), top_k=5, final_benchmark=True)


@pytest.mark.parametrize(
    "results",
    (
        (
            RetrievalResult("bm25", "aib-assets-2023", "a", 1, 1.0, True, "unverified"),
            RetrievalResult("bm25", "aib-assets-2023", "b", 1, 0.5, True, "unverified"),
        ),
        (
            RetrievalResult("bm25", "aib-assets-2023", "b", 1, 1.0, True, "unverified"),
            RetrievalResult("bm25", "aib-assets-2023", "a", 2, 1.0, True, "unverified"),
        ),
    ),
)
def test_final_boundary_rejects_duplicate_or_noncanonical_ranks(
    results: tuple[RetrievalResult, ...],
) -> None:
    methods = list(_final_hostile_methods())
    methods[0].results = results

    with pytest.raises(ValueError, match="canonical ranks and score ordering"):
        compare_retrievers(methods, frozen_question(), top_k=5, final_benchmark=True)


@pytest.mark.parametrize("score", (float("nan"), float("inf"), float("-inf")))
def test_final_boundary_rejects_non_finite_scores(score: float) -> None:
    methods = list(_final_hostile_methods())
    methods[0].results = (
        RetrievalResult("bm25", "aib-assets-2023", "bad-score", 1, score, True, "unverified"),
    )

    with pytest.raises(ValueError, match="finite"):
        compare_retrievers(methods, frozen_question(), top_k=5, final_benchmark=True)


def test_comparison_boundary_passes_one_cutoff_and_normalizes_hostile_outputs() -> None:
    methods = _hostile_methods()

    compared = compare_retrievers(methods, frozen_question(), top_k=5)

    assert set(compared) == set(REGISTERED_METHOD_IDS)
    assert all(method.received_top_k == 5 for method in methods)
    assert all(len(results) == 5 for results in compared.values())
    assert all([item.rank for item in results] == [1, 2, 3, 4, 5] for results in compared.values())
    assert all(results[0].evidence_id.endswith("-00") for results in compared.values())


def test_comparison_boundary_rejects_duplicate_unknown_and_malformed_results() -> None:
    methods = list(_hostile_methods())
    methods[-1].method_name = "unknown"
    with pytest.raises(ValueError, match="registered"):
        compare_retrievers(methods, frozen_question())

    duplicate = _hostile_methods()
    duplicate[1].method_name = duplicate[0].method_name
    with pytest.raises(ValueError, match="duplicate"):
        compare_retrievers(duplicate, frozen_question())

    malformed = list(_hostile_methods())
    first = malformed[0]
    first.results = (
        RetrievalResult(first.method_name, "wrong-question", "same", 1, 1.0, True, "unverified"),
        RetrievalResult(first.method_name, "wrong-question", "same", 2, 0.5, True, "unverified"),
    )
    with pytest.raises(ValueError, match="question_id|unique"):
        compare_retrievers(malformed, frozen_question())


@pytest.mark.parametrize("method", all_methods(), ids=lambda item: item.method_name)
def test_retrieval_does_not_accept_gold_labels_and_is_deterministic(method) -> None:
    assert "gold" not in str(signature(method.retrieve)).lower()

    with pytest.raises(TypeError):
        method.retrieve(frozen_question(), gold_labels={"aib-assets-2023": {"aib-2023"}})  # type: ignore[call-arg]

    first = method.retrieve(frozen_question())
    second = method.retrieve(frozen_question())
    assert first == second
    assert all(isinstance(result, RetrievalResult) for result in first)


def test_retriever_visible_corpus_has_no_evaluation_annotations() -> None:
    assert {field.name for field in fields(CorpusRecord)} == {
        "evidence_id", "issuer", "valid_time", "text", "numeric_value", "source_time"
    }


def test_retriever_visible_query_has_no_evaluator_only_fields() -> None:
    assert {field.name for field in fields(Question)} == {"question_id", "issuer", "query", "cutoff", "source_cutoff"}


def test_verifier_status_is_derived_from_retrieval_context_not_a_corpus_annotation() -> None:
    verifier = {method.method_name: method for method in all_methods()}["temporal_kg_verify"]

    results = verifier.retrieve(frozen_question())

    assert {result.verification_status for result in results} <= {"time_verified", "unverified"}


def test_temporal_kg_uses_the_label_free_temporal_evidence_graph() -> None:
    evidence = EvidenceSpanV1(
        schema_version="evidence-span.v1",
        document_id="aib-2022",
        issuer_id="AIB",
        report_period="2022",
        source_date=date(2023, 2, 1),
        page_id="p1",
        block_id="assets",
        bbox=(0.0, 0.0, 1.0, 1.0),
        section="Assets",
        text="AIB total assets",
        text_hash="0" * 64,
        extraction_confidence=1.0,
        provider="fixture",
        content_hash="1" * 64,
    )
    graph = build_graph(evidence_spans=[evidence])
    with_graph = {
        method.method_name: method
        for method in all_retrievers(frozen_corpus(), cutoff=frozen_question().cutoff, graph=graph, mode="fixture")
    }["temporal_kg"]

    assert {result.evidence_id for result in with_graph.retrieve(frozen_question())} == {"aib-2022"}


def test_temporal_methods_exclude_future_evidence_while_static_method_reports_it_as_stale() -> None:
    methods = {method.method_name: method for method in all_methods()}
    question = Question("aib-assets-2023", "AIB", "AIB total assets", date(2023, 12, 31))

    static_results = methods["static_kg"].retrieve(question)
    temporal_results = methods["temporal_kg"].retrieve(question)

    assert any(result.evidence_id == "aib-2024" and not result.valid_time_match for result in static_results)
    assert "aib-2024" not in {result.evidence_id for result in temporal_results}


def test_metric_fixture_reports_retrieval_temporal_and_audit_metrics() -> None:
    results = {
        "aib-assets-2023": (
            RetrievalResult("temporal_kg_verify", "aib-assets-2023", "aib-2023", 1, 1.0, True, "verified"),
            RetrievalResult("temporal_kg_verify", "aib-assets-2023", "aib-conflict", 2, 0.9, True, "contradiction"),
        ),
        "esb-employees-2024": (
            RetrievalResult("temporal_kg_verify", "esb-employees-2024", "esb-2023", 1, 1.0, False, "unverified"),
        ),
    }
    labels = EvaluationLabels(
        relevant_evidence={"aib-assets-2023": frozenset({"aib-2023"}), "esb-employees-2024": frozenset({"esb-2024"})},
        issuer_by_question={"aib-assets-2023": "AIB", "esb-employees-2024": "ESB"},
        contradiction_evidence={"aib-assets-2023": frozenset({"aib-conflict"})},
        citation_evidence={"aib-assets-2023": frozenset({"aib-2023"}), "esb-employees-2024": frozenset({"esb-2024"})},
        expected_numeric={"aib-assets-2023": 136.3, "esb-employees-2024": 9588.0},
    )

    metrics = score_retrieval(results, labels, numeric_predictions={"aib-assets-2023": 136.3, "esb-employees-2024": 9000.0})

    assert metrics.recall_at_5 == pytest.approx(0.5)
    assert metrics.mrr == pytest.approx(0.5)
    assert metrics.ndcg_at_5 == pytest.approx(0.5)
    assert metrics.temporal_accuracy == pytest.approx(0.5)
    assert metrics.stale_evidence_rate == pytest.approx(1 / 3)
    assert metrics.contradiction_f1 == pytest.approx(1.0)
    assert metrics.citation_accuracy == pytest.approx(0.5)
    assert metrics.numerical_mismatch == pytest.approx(0.5)


def test_recall_at_five_counts_each_relevant_evidence_item() -> None:
    results = {
        "q1": (RetrievalResult("bm25", "q1", "evidence-a", 1, 1.0, True, "unverified"),),
    }
    labels = EvaluationLabels(
        relevant_evidence={"q1": frozenset({"evidence-a", "evidence-b"})},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence={},
        citation_evidence={"q1": frozenset({"evidence-a"})},
        expected_numeric={},
    )

    metrics = score_retrieval(results, labels)

    assert metrics.recall_at_5 == pytest.approx(0.5)


def test_numeric_mismatch_is_binary_and_reports_missing_prediction_coverage() -> None:
    labels = EvaluationLabels(
        relevant_evidence={"q1": frozenset(), "q2": frozenset(), "q3": frozenset()},
        issuer_by_question={"q1": "AIB", "q2": "AIB", "q3": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={"q1": 42.0, "q2": 10.0, "q3": 7.0},
    )

    metrics = score_retrieval({}, labels, numeric_predictions={"q1": "42", "q2": 11.0})

    assert metrics.evaluable_question_count == 3
    assert metrics.prediction_count == 2
    assert metrics.answer_coverage == pytest.approx(2 / 3)
    assert metrics.mismatch_count == 2
    assert metrics.mismatch_denominator == 3
    assert metrics.mismatch_rate == pytest.approx(2 / 3)
    assert metrics.numerical_mismatch == pytest.approx(2 / 3)


def test_hit_and_recall_are_distinct_and_zero_gold_is_explicitly_non_evaluable() -> None:
    results = {
        "one": (RetrievalResult("bm25", "one", "gold-1", 1, 1.0, True, "unverified"),),
        "two": (
            RetrievalResult("bm25", "two", "gold-1", 1, 1.0, True, "unverified"),
            RetrievalResult("bm25", "two", "gold-2", 2, 0.9, True, "unverified"),
            RetrievalResult("bm25", "two", "gold-2", 3, 0.8, True, "unverified"),
        ),
        "none": (RetrievalResult("bm25", "none", "anything", 1, 1.0, True, "unverified"),),
    }
    labels = EvaluationLabels(
        relevant_evidence={
            "one": frozenset({"gold-1", "gold-2", "gold-3", "gold-4"}),
            "two": frozenset({"gold-1", "gold-2", "gold-3", "gold-4"}),
            "none": frozenset(),
        },
        issuer_by_question={"one": "AIB", "two": "AIB", "none": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={},
    )

    metrics = score_retrieval(results, labels)

    assert metrics.hit_at_5 == pytest.approx(2 / 3)
    assert metrics.recall_at_5 == pytest.approx((0.25 + 0.5) / 2)
    assert metrics.recall_evaluable_question_count == 2
    assert metrics.zero_gold_question_count == 1


def test_retrievers_expose_frozen_metadata_and_final_benchmark_rejects_fixtures() -> None:
    methods = all_methods()

    assert all(method.metadata.implementation_mode == "fixture" for method in methods)
    assert all({field.name for field in fields(method.metadata)} == {
        "method_id", "implementation_mode", "backend", "model_name", "model_revision",
        "uses_graph", "uses_temporal_filter", "uses_reranker", "uses_verification",
        "backend_status",
    } for method in methods)
    with pytest.raises((AttributeError, TypeError)):
        methods[0].metadata.backend = "mutated"  # type: ignore[misc]
    with pytest.raises(ValueError, match="fixture"):
        validate_final_benchmark(methods)
    assert retrieval_manifest(methods) == {method.method_name: method.metadata for method in methods}
    with pytest.raises(ValueError, match="production metadata"):
        RetrievalMetadata("bm25", "production", "", None, None, False, True, False, False).validate()


def test_production_factory_fails_closed_while_reranker_revision_is_unverified() -> None:
    """Fail-loud behavior is not counted as successful production execution."""
    corpus = frozen_corpus()
    graph = source_graph(corpus)

    with pytest.raises(RuntimeError, match="Failed to load production"):
        all_retrievers(corpus, cutoff=frozen_question().cutoff, graph=graph, mode="production")


def test_fixture_retrievers_reject_gold_shaped_inputs() -> None:
    """Verify fixture retrievers also reject gold-shaped inputs."""
    methods = all_methods()  # fixture mode

    class GoldShapedQuery:
        question_id = "aib-assets-2023"
        issuer = "AIB"
        query = "AIB assets"
        cutoff = date(2023, 12, 31)
        gold_answer = "136.3"
        gold_source_ids = ("aib-2023",)

    for method in methods:
        with pytest.raises(TypeError, match="RetrieverQuery"):
            method.retrieve(GoldShapedQuery())  # type: ignore[arg-type]


def test_retrieval_rejects_gold_shaped_inputs_and_does_not_open_label_files(monkeypatch: pytest.MonkeyPatch) -> None:
    class GoldShapedQuery:
        question_id = "aib-assets-2023"
        issuer = "AIB"
        query = "AIB assets"
        cutoff = date(2023, 12, 31)
        gold_answer = "136.3"
        gold_source_ids = ("aib-2023",)

    for method in all_methods():
        with pytest.raises(TypeError, match="RetrieverQuery"):
            method.retrieve(GoldShapedQuery())  # type: ignore[arg-type]

    def fail_label_access(*args: object, **kwargs: object) -> object:
        if args and "labels" in str(args[0]).replace("\\", "/"):
            raise AssertionError("retrieval opened a label file")
        return original_open(*args, **kwargs)

    import builtins
    original_open = builtins.open
    monkeypatch.setattr(builtins, "open", fail_label_access)
    for method in all_methods():
        method.retrieve(frozen_question())


def test_evaluator_only_graph_edges_are_not_retriever_visible_and_source_graph_still_retrieves() -> None:
    from ecoquant.evidence_graph.graph import Relation, TemporalEvidenceGraph
    from ecoquant.evidence_graph.models import Claim

    graph = TemporalEvidenceGraph()
    older = Claim("old", "AIB", "assets", 1, True, "source", date(2023, 1, 1), date(2023, 1, 1))
    newer = Claim("new", "AIB", "assets", 2, True, "source", date(2024, 1, 1), date(2024, 1, 1))
    graph.add_node(older)
    graph.add_node(newer)
    graph.add_edge(newer.id, older.id, Relation.CONTRADICTS, evaluator_only=True)
    assert graph.retrieval_edges() == ()

    source_graph = build_graph(evidence_spans=[
        EvidenceSpanV1("evidence-span.v1", "aib-2023", "AIB", "2023", date(2024, 2, 1), "p1", "b1", (0, 0, 1, 1), "Assets", "AIB total assets", "0" * 64, 1.0, "fixture", "1" * 64)
    ])
    method = {item.method_name: item for item in all_retrievers(frozen_corpus(), cutoff=frozen_question().cutoff, graph=source_graph, mode="fixture")}["static_kg"]
    assert "aib-2023" in {result.evidence_id for result in method.retrieve(frozen_question())}


def test_kg_paths_require_the_typed_retrieval_safe_graph_boundary() -> None:
    with pytest.raises(ValueError, match="TemporalEvidenceGraph"):
        StaticKGRetriever(frozen_corpus(), cutoff=frozen_question().cutoff)
    with pytest.raises(ValueError, match="TemporalEvidenceGraph"):
        StaticKGRetriever(frozen_corpus(), cutoff=frozen_question().cutoff, graph=object())

    methods = {item.method_name: item for item in all_methods()}

    rerank_calls: list[str] = []
    verify_calls: list[str] = []
    methods["temporal_kg_rerank"].reranker = lambda record, question, score: rerank_calls.append(record.evidence_id) or score
    methods["temporal_kg_verify"].verifier = lambda record, question: verify_calls.append(record.evidence_id) or "source_verified"
    methods["temporal_kg_rerank"].retrieve(frozen_question())
    methods["temporal_kg_verify"].retrieve(frozen_question())

    assert rerank_calls
    assert verify_calls
    assert not methods["bm25"].metadata.uses_graph
    assert not methods["dense"].metadata.uses_graph


def test_kg_candidates_require_a_source_derived_graph_path_and_honor_source_cutoff() -> None:
    source = EvidenceSpanV1("evidence-span.v1", "aib-2023", "AIB", "2023", date(2024, 2, 1), "p1", "b1", (0, 0, 1, 1), "Assets", "AIB total assets", "0" * 64, 1.0, "fixture", "1" * 64)
    graph = build_graph(evidence_spans=[source])
    methods = {item.method_name: item for item in all_retrievers(frozen_corpus(), cutoff=date(2023, 12, 31), graph=graph, mode="fixture")}
    query = Question("q", "AIB", "AIB total assets", date(2023, 12, 31), source_cutoff=date(2023, 12, 31))

    assert "aib-2023" in {r.evidence_id for r in methods["static_kg"].retrieve(query)}
    assert "aib-2023" not in {r.evidence_id for r in methods["temporal_kg"].retrieve(query)}
    assert methods["temporal_kg"].retrieve(query) == methods["temporal_kg"].retrieve(query)


def test_kg_ranking_resolves_only_graph_reachable_ids_without_scanning_corpus() -> None:
    records = tuple(
        CorpusRecord(
            f"record-{index}",
            "AIB",
            date(2023, 12, 31),
            "AIB total assets exact answer" if index else "AIB weak evidence",
            source_time=date(2023, 1, 1),
        )
        for index in range(20)
    )
    graph = TemporalEvidenceGraph()
    graph.add_node(Issuer("AIB", date(2023, 1, 1), date(2023, 1, 1), "AIB"))
    graph.add_node(Document("record-0", date(2023, 12, 31), date(2023, 1, 1), "AIB"))
    graph.add_edge("AIB", "record-0", Relation.CONTAINS)
    method = {
        item.method_name: item
        for item in all_retrievers(records, cutoff=date(2023, 12, 31), graph=graph, mode="fixture")
    }["static_kg"]

    class NoQueryTimeCorpusScan:
        def __iter__(self):
            raise AssertionError("KG query enumerated the complete corpus")

    method.corpus = NoQueryTimeCorpusScan()  # type: ignore[assignment]
    results = method.retrieve(Question("q", "AIB", "total assets exact answer", date(2023, 12, 31)))

    assert [result.evidence_id for result in results] == ["record-0"]


def test_removing_source_derived_graph_path_removes_retrieval_candidate() -> None:
    corpus = (
        CorpusRecord(
            "reachable",
            "AIB",
            date(2023, 12, 31),
            "AIB assets",
            source_time=date(2023, 1, 1),
        ),
    )
    graph = source_graph(corpus)
    method = {
        item.method_name: item
        for item in all_retrievers(corpus, cutoff=date(2023, 12, 31), graph=graph, mode="fixture")
    }["static_kg"]
    query = Question("q", "AIB", "AIB assets", date(2023, 12, 31))

    assert [result.evidence_id for result in method.retrieve(query)] == ["reachable"]
    graph.remove_edge("AIB", "reachable", Relation.CONTAINS)
    assert method.retrieve(query) == ()


@pytest.mark.parametrize("evaluator_relation", (Relation.CONTRADICTS, Relation.SUPERSEDES))
def test_evaluator_only_edges_cannot_create_retrieval_paths_or_access_labels(
    monkeypatch: pytest.MonkeyPatch, evaluator_relation: Relation
) -> None:
    graph = TemporalEvidenceGraph()
    graph.add_node(Issuer("AIB", date(2023, 1, 1), date(2023, 1, 1), "AIB"))
    graph.add_node(Document("aib-2023", date(2023, 12, 31), date(2023, 1, 1), "AIB"))
    graph.add_edge("AIB", "aib-2023", evaluator_relation, evaluator_only=True)
    method = {item.method_name: item for item in all_retrievers(frozen_corpus(), cutoff=date(2023, 12, 31), graph=graph, mode="fixture")}["static_kg"]

    import builtins
    original_open = builtins.open

    def fail_label_access(*args: object, **kwargs: object) -> object:
        if args and "labels" in str(args[0]).replace("\\", "/"):
            raise AssertionError("retrieval opened a label file")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", fail_label_access)
    before = method.retrieve(frozen_question())
    graph.add_edge("AIB", "aib-2023", Relation.CONTAINS)
    after = method.retrieve(frozen_question())

    assert "aib-2023" not in {r.evidence_id for r in before}
    assert "aib-2023" in {r.evidence_id for r in after}


def test_temporal_kg_applies_valid_and_source_time_independently_when_their_order_is_inverted() -> None:
    valid_before_source = CorpusRecord("published-late", "AIB", date(2023, 12, 31), "AIB assets", source_time=date(2024, 1, 1))
    source_before_valid = CorpusRecord("valid-late", "AIB", date(2024, 12, 31), "AIB assets", source_time=date(2023, 1, 1))
    corpus = (valid_before_source, source_before_valid)
    method = {
        item.method_name: item
        for item in all_retrievers(corpus, cutoff=date(2023, 12, 31), graph=source_graph(corpus), mode="fixture")
    }["temporal_kg"]
    query = Question("q", "AIB", "AIB assets", date(2023, 12, 31), source_cutoff=date(2023, 12, 31))

    assert method.retrieve(query) == ()


def test_verifier_distinguishes_valid_and_source_time_failures() -> None:
    verifier = {method.method_name: method for method in all_methods()}["temporal_kg_verify"]
    query = Question("q", "AIB", "AIB assets", date(2023, 12, 31), source_cutoff=date(2023, 12, 31))
    valid_before_source = CorpusRecord("published-late", "AIB", date(2023, 12, 31), "AIB assets", source_time=date(2024, 1, 1))
    source_before_valid = CorpusRecord("valid-late", "AIB", date(2024, 12, 31), "AIB assets", source_time=date(2023, 1, 1))

    assert verifier._verification_status(valid_before_source, query) == "published_after_source_cutoff"  # type: ignore[attr-defined]
    assert verifier._verification_status(source_before_valid, query) == "invalid_for_requested_time"  # type: ignore[attr-defined]


def test_verifier_uses_authoritative_linked_document_source_time() -> None:
    record = CorpusRecord("linked", "AIB", date(2023, 12, 31), "AIB assets", source_time=None)
    graph = TemporalEvidenceGraph()
    graph.add_node(Issuer("AIB", date(2023, 1, 1), date(2023, 1, 1), "AIB"))
    graph.add_node(Document("linked", date(2023, 12, 31), date(2024, 1, 1), "AIB"))
    graph.add_edge("AIB", "linked", Relation.CONTAINS)
    verifier = {
        method.method_name: method
        for method in all_retrievers((record,), cutoff=date(2023, 12, 31), graph=graph, mode="fixture")
    }["temporal_kg_verify"]

    query_2023 = Question("q", "AIB", "assets", date(2023, 12, 31), source_cutoff=date(2023, 12, 31))
    query_2024 = Question("q", "AIB", "assets", date(2023, 12, 31), source_cutoff=date(2024, 1, 1))

    assert verifier._verification_status(record, query_2023) == "published_after_source_cutoff"  # type: ignore[attr-defined]
    assert verifier._verification_status(record, query_2024) == "time_verified"  # type: ignore[attr-defined]


def test_verifier_reports_missing_source_time_without_authoritative_document_time() -> None:
    record = CorpusRecord("missing-time", "AIB", date(2023, 12, 31), "AIB assets", source_time=None)
    graph = TemporalEvidenceGraph()
    graph.add_node(Issuer("AIB", date(2023, 1, 1), date(2023, 1, 1), "AIB"))
    graph.add_node(Document("missing-time", date(2023, 12, 31), None, "AIB"))
    graph.add_edge("AIB", "missing-time", Relation.CONTAINS)
    verifier = {
        method.method_name: method
        for method in all_retrievers((record,), cutoff=date(2023, 12, 31), graph=graph, mode="fixture")
    }["temporal_kg_verify"]
    query = Question("q", "AIB", "assets", date(2023, 12, 31), source_cutoff=date(2023, 12, 31))

    assert verifier._verification_status(record, query) == "missing_source_time"  # type: ignore[attr-defined]
    assert verifier.retrieve(query) == ()


def test_paired_issuer_clustered_bootstrap_is_seeded_and_clusters_by_issuer() -> None:
    baseline = {"q1": 0.0, "q2": 0.0, "q3": 1.0, "q4": 1.0}
    candidate = {"q1": 1.0, "q2": 1.0, "q3": 1.0, "q4": 1.0}
    issuers = {"q1": "AIB", "q2": "AIB", "q3": "ESB", "q4": "ESB"}

    first = paired_issuer_clustered_bootstrap(baseline, candidate, issuers, samples=200)
    second = paired_issuer_clustered_bootstrap(baseline, candidate, issuers, samples=200)

    assert first == second
    assert first.seed == 20260710
    assert first.point_estimate == pytest.approx(0.5)
    assert first.lower <= first.point_estimate <= first.upper
    assert first.cluster_count == 2


def test_page_and_block_accuracy_at_five_use_catalog_identity_and_macro_aggregation() -> None:
    def result(question_id: str, evidence_id: str, rank: int) -> RetrievalResult:
        return RetrievalResult("bm25", question_id, evidence_id, rank, 6.0 - rank, True, "unverified")

    results = {
        "page-rank-1": (result("page-rank-1", "p1", 1),),
        "page-rank-5": tuple(result("page-rank-5", f"p5-{rank}", rank) for rank in range(1, 6)),
        "page-miss": (result("page-miss", "miss", 1),),
        "block-only": (result("block-only", "block", 1),),
        "unannotated": (result("unannotated", "ignored", 1),),
    }
    labels = EvaluationLabels(
        relevant_evidence={question_id: frozenset() for question_id in results},
        issuer_by_question={question_id: "AIB" for question_id in results},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={},
        gold_page_ids={
            "page-rank-1": frozenset({"gold-page", "alternate-page"}),
            "page-rank-5": frozenset({"rank-five-page"}),
            "page-miss": frozenset({"gold-page"}),
        },
        gold_block_ids={
            "page-rank-1": frozenset({"different-block"}),
            "page-rank-5": frozenset({"rank-five-block", "alternate-block"}),
            "block-only": frozenset({"gold-block"}),
        },
    )
    catalog = {
        "p1": EvidenceLocation("gold-page", "wrong-block"),
        **{f"p5-{rank}": EvidenceLocation("other-page", "other-block") for rank in range(1, 5)},
        "p5-5": EvidenceLocation("rank-five-page", "rank-five-block"),
        "miss": EvidenceLocation("wrong-page", "wrong-block"),
        "block": EvidenceLocation("page-without-gold", "gold-block"),
        "ignored": EvidenceLocation("ignored-page", "ignored-block"),
    }

    metrics = score_retrieval(results, labels, evidence_catalog=catalog)

    assert metrics.page_accuracy_at_5 == pytest.approx(2 / 3)
    assert metrics.block_accuracy_at_5 == pytest.approx(2 / 3)
    assert metrics.evaluable_page_questions == 3
    assert metrics.evaluable_block_questions == 3
    assert metrics.non_evaluable_page_questions == 2
    assert metrics.non_evaluable_block_questions == 2


def test_page_and_block_accuracy_are_portably_non_evaluable_without_gold_annotations() -> None:
    labels = EvaluationLabels(
        relevant_evidence={"q1": frozenset()},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={},
    )

    metrics = score_retrieval({}, labels, evidence_catalog={})

    assert metrics.page_accuracy_at_5 is None
    assert metrics.block_accuracy_at_5 is None
    assert metrics.page_accuracy_reason == "no_gold_page_annotations"
    assert metrics.block_accuracy_reason == "no_gold_block_annotations"


def test_citation_metric_rejects_missing_catalog_entries_for_returned_evidence() -> None:
    results = {
        "q1": (RetrievalResult("bm25", "q1", "missing", 1, 1.0, True, "unverified"),),
    }
    labels = EvaluationLabels(
        relevant_evidence={"q1": frozenset()},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={},
        gold_page_ids={"q1": frozenset({"page-1"})},
    )

    with pytest.raises(ValueError, match="missing evidence catalog entry"):
        score_retrieval(results, labels, evidence_catalog={})


def test_empty_contradiction_reference_and_prediction_are_portably_non_evaluable() -> None:
    labels = EvaluationLabels(
        relevant_evidence={"q1": frozenset()},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={},
    )

    metrics = score_retrieval({}, labels)

    assert metrics.contradiction_f1 is None
    assert metrics.contradiction_evaluable is False
    assert metrics.contradiction_reason == "no_positive_reference_or_prediction"


# ---------------------------------------------------------------------------
# Tests: Canonical corpus fingerprint
# ---------------------------------------------------------------------------


class TestCorpusFingerprint:
    """Corpus fingerprint must be deterministic and corpus-sensitive."""

    @staticmethod
    def _legacy_delimiter_payload(corpus: tuple[CorpusRecord, ...]) -> bytes:
        """Reproduce the superseded ambiguous encoding for the RED fixture."""
        rows = []
        for record in sorted(corpus, key=lambda item: item.evidence_id):
            rows.append("|".join((
                "1",
                record.evidence_id,
                record.issuer,
                record.valid_time.isoformat(),
                record.source_time.isoformat() if record.source_time else "",
                record.text.strip().lower(),
                str(record.numeric_value) if record.numeric_value is not None else "",
            )))
        return "\n".join(rows).encode("utf-8")

    def test_fingerprint_is_deterministic(self) -> None:
        corpus = frozen_corpus()
        fp1 = corpus_fingerprint(corpus)
        fp2 = corpus_fingerprint(corpus)
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_fingerprint_is_order_independent(self) -> None:
        corpus = frozen_corpus()
        reversed_corpus = tuple(reversed(corpus))
        assert corpus_fingerprint(corpus) == corpus_fingerprint(reversed_corpus)

    def test_different_corpus_produces_different_fingerprint(self) -> None:
        corpus_a = frozen_corpus()
        corpus_b = (
            CorpusRecord("x-2022", "X", date(2022, 12, 31), "Different text", 99.9),
            CorpusRecord("x-2023", "X", date(2023, 12, 31), "More text", 100.0),
        )
        assert corpus_fingerprint(corpus_a) != corpus_fingerprint(corpus_b)

    def test_equal_length_different_corpus_fails_fingerprint_comparison(self) -> None:
        """Two corpora with the same number of records but different content
        must produce different fingerprints."""
        corpus_a = (
            CorpusRecord("a-1", "A", date(2023, 12, 31), "Alpha text", 1.0),
            CorpusRecord("a-2", "A", date(2024, 12, 31), "Beta text", 2.0),
        )
        corpus_b = (
            CorpusRecord("b-1", "B", date(2023, 12, 31), "Gamma text", 3.0),
            CorpusRecord("b-2", "B", date(2024, 12, 31), "Delta text", 4.0),
        )
        assert len(corpus_a) == len(corpus_b)
        assert corpus_fingerprint(corpus_a) != corpus_fingerprint(corpus_b)

    def test_corpus_fingerprint_rejects_delimiter_collision(self) -> None:
        corpus_a = (
            CorpusRecord(
                "a|b", "c", date(2023, 12, 31), "same", 1.0, date(2024, 1, 1)
            ),
        )
        corpus_b = (
            CorpusRecord(
                "a", "b|c", date(2023, 12, 31), "same", 1.0, date(2024, 1, 1)
            ),
        )

        assert corpus_a != corpus_b
        assert self._legacy_delimiter_payload(corpus_a) == self._legacy_delimiter_payload(corpus_b)
        assert corpus_fingerprint(corpus_a) != corpus_fingerprint(corpus_b)

    def test_final_boundary_rejects_delimiter_collision_corpora(self) -> None:
        corpus_a = (
            CorpusRecord(
                "a|b", "c", date(2023, 12, 31), "same", 1.0, date(2024, 1, 1)
            ),
        )
        corpus_b = (
            CorpusRecord(
                "a", "b|c", date(2023, 12, 31), "same", 1.0, date(2024, 1, 1)
            ),
        )
        methods = list(_final_hostile_methods(corpus_a))
        methods[-1] = _FinalHostileRetriever(methods[-1].method_name, corpus_b)

        with pytest.raises(ValueError, match="corpus fingerprint"):
            compare_retrievers(methods, frozen_question(), top_k=5, final_benchmark=True)

    def test_single_record_change_breaks_fingerprint(self) -> None:
        corpus = frozen_corpus()
        fp_original = corpus_fingerprint(corpus)
        # Change numeric_value of one record
        modified = tuple(
            CorpusRecord(r.evidence_id, r.issuer, r.valid_time, r.text, 999.9 if r.evidence_id == "aib-2022" else r.numeric_value, r.source_time)
            for r in corpus
        )
        assert corpus_fingerprint(modified) != fp_original

    def test_source_time_and_valid_time_changes_break_fingerprint(self) -> None:
        record = CorpusRecord(
            "evidence-1", "AIB", date(2023, 12, 31), "AIB assets", 1.0, date(2024, 1, 1)
        )
        changed_source = CorpusRecord(
            "evidence-1", "AIB", date(2023, 12, 31), "AIB assets", 1.0, date(2024, 1, 2)
        )
        changed_valid = CorpusRecord(
            "evidence-1", "AIB", date(2024, 12, 31), "AIB assets", 1.0, date(2024, 1, 1)
        )

        assert corpus_fingerprint((record,)) != corpus_fingerprint((changed_source,))
        assert corpus_fingerprint((record,)) != corpus_fingerprint((changed_valid,))

    def test_normalized_text_change_breaks_fingerprint(self) -> None:
        original = CorpusRecord("evidence-1", "AIB", date(2023, 12, 31), "AIB assets")
        changed = CorpusRecord("evidence-1", "AIB", date(2023, 12, 31), "AIB liabilities")

        assert corpus_fingerprint((original,)) != corpus_fingerprint((changed,))

    def test_unicode_text_uses_nfkc_normalization(self) -> None:
        composed = CorpusRecord("evidence-1", "AIB", date(2023, 12, 31), "Caf\u00e9 assets")
        decomposed = CorpusRecord("evidence-1", "AIB", date(2023, 12, 31), "Cafe\u0301 assets")

        assert corpus_fingerprint((composed,)) == corpus_fingerprint((decomposed,))

    def test_numeric_null_is_not_ambiguous_with_empty_string(self) -> None:
        valid = CorpusRecord("evidence-1", "AIB", date(2023, 12, 31), "AIB assets", None)
        invalid = CorpusRecord(
            "evidence-1", "AIB", date(2023, 12, 31), "AIB assets", ""  # type: ignore[arg-type]
        )

        assert len(corpus_fingerprint((valid,))) == 64
        with pytest.raises(ValueError, match="numeric_value must be a finite number or None"):
            corpus_fingerprint((invalid,))

    @pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
    def test_non_finite_numeric_values_are_rejected(self, value: float) -> None:
        record = CorpusRecord("evidence-1", "AIB", date(2023, 12, 31), "AIB assets", value)

        with pytest.raises(ValueError, match="numeric_value must be a finite number or None"):
            corpus_fingerprint((record,))
