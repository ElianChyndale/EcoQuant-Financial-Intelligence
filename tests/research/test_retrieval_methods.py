from __future__ import annotations

from datetime import date
from dataclasses import fields
from inspect import signature
import math

import pytest

from ecoquant.retrieval.base import CorpusRecord, Question, RetrievalResult, all_retrievers
from ecoquant.retrieval.evaluation import (
    EvaluationLabels,
    paired_issuer_clustered_bootstrap,
    score_retrieval,
)
from ecoquant.evidence_graph.builder import build_graph
from ecoquant.document_intelligence.schema import EvidenceSpanV1


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


def all_methods():
    return all_retrievers(frozen_corpus(), cutoff=frozen_question().cutoff)


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
    with pytest.raises(ValueError, match="fixed top_k=5"):
        all_methods()[0].retrieve(frozen_question(), top_k=2)


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
        "evidence_id", "issuer", "valid_time", "text", "numeric_value"
    }


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
    without_graph = {method.method_name: method for method in all_methods()}["temporal_kg"]
    with_graph = {
        method.method_name: method
        for method in all_retrievers(frozen_corpus(), cutoff=frozen_question().cutoff, graph=graph)
    }["temporal_kg"]

    plain_scores = {result.evidence_id: result.score for result in without_graph.retrieve(frozen_question())}
    graph_scores = {result.evidence_id: result.score for result in with_graph.retrieve(frozen_question())}

    assert graph_scores["aib-2022"] > plain_scores["aib-2022"]


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
    assert metrics.numerical_mismatch == pytest.approx(294.0)


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


def test_missing_numeric_predictions_are_reported_as_infinite_mismatch() -> None:
    labels = EvaluationLabels(
        relevant_evidence={"q1": frozenset()},
        issuer_by_question={"q1": "AIB"},
        contradiction_evidence={},
        citation_evidence={},
        expected_numeric={"q1": 42.0},
    )

    metrics = score_retrieval({}, labels, numeric_predictions={})

    assert math.isinf(metrics.numerical_mismatch)


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
