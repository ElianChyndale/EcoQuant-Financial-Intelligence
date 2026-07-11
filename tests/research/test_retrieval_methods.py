from __future__ import annotations

from datetime import date
from dataclasses import fields
from inspect import signature

import pytest

from ecoquant.retrieval.base import (
    REGISTERED_METHOD_IDS,
    CorpusRecord,
    Question,
    RetrievalMetadata,
    RetrievalResult,
    all_retrievers,
    compare_retrievers,
    validate_final_benchmark,
    retrieval_manifest,
)
from ecoquant.retrieval.evaluation import (
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
    } for method in methods)
    with pytest.raises((AttributeError, TypeError)):
        methods[0].metadata.backend = "mutated"  # type: ignore[misc]
    with pytest.raises(ValueError, match="fixture"):
        validate_final_benchmark(methods)
    assert retrieval_manifest(methods) == {method.method_name: method.metadata for method in methods}
    with pytest.raises(ValueError, match="production metadata"):
        RetrievalMetadata("bm25", "production", "", None, None, False, True, False, False).validate()


def test_production_retrievers_have_production_metadata() -> None:
    """Verify production-mode retrievers have production metadata.

    In production mode, model-loading failures raise RuntimeError rather than
    silently degrading. This test verifies either successful loading or proper
    error raising.
    """
    corpus = frozen_corpus()
    graph = source_graph(corpus)

    try:
        production_methods = all_retrievers(corpus, cutoff=frozen_question().cutoff, graph=graph, mode="production")
        # Models loaded successfully
        for method in production_methods:
            assert method.metadata.implementation_mode == "production"
            assert method.metadata.backend is not None and method.metadata.backend != ""
            # Model name and revision may be None for graph-based methods
            if method.method_name in ("bm25", "dense", "temporal_kg_rerank", "temporal_kg_verify"):
                assert method.metadata.model_name is not None
                assert method.metadata.model_revision is not None
    except RuntimeError as e:
        # Model not available - verify the error message is clear
        assert "Failed to load production" in str(e)
        assert "A production run must not silently fall back" in str(e)


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
