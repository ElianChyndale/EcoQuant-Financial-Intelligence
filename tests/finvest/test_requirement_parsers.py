from __future__ import annotations

import pytest

from finvest.requirement_graph.parsers import (
    deterministic_finance_parser,
    graph_quality,
    structured_llm_parser,
    trainable_parser,
)
from finvest.benchmark.schemas import RequirementGraph, RequirementNode


def test_parser_extracts_entity_metric_period() -> None:
    parsed = deterministic_finance_parser("What is Apple total revenue for fiscal year 2024?")
    node_types = {n.node_type for n in parsed.graph.nodes}
    assert "ENTITY" in node_types
    assert "METRIC" in node_types
    assert "PERIOD" in node_types
    assert any(n.value == "FY2024" for n in parsed.graph.nodes)
    assert 0.0 < parsed.score <= 1.0


def test_parser_fcff_derivation() -> None:
    parsed = deterministic_finance_parser("What is MSFT free cash flow for fiscal 2025?")
    node_values = {n.value for n in parsed.graph.nodes}
    assert "FCFF" in node_values or "fcff" in node_values
    # FCFF derives from OCF and Capex.
    relations = {(e.source_id, e.target_id) for e in parsed.graph.edges}
    assert ("metric", "ocf") in relations
    assert ("metric", "capex") in relations


def test_parser_validates_graph() -> None:
    parsed = deterministic_finance_parser("What is Apple net income for fiscal year 2023?")
    parsed.graph.validate()  # no raise


def test_llm_parser_returns_none_without_key() -> None:
    assert structured_llm_parser("question", api_key=None) is None


def test_trainable_parser_returns_none_scaffold() -> None:
    assert trainable_parser("question") is None


def test_graph_quality_metrics() -> None:
    gold = RequirementGraph(
        nodes=(RequirementNode("e", "ENTITY", "AAPL"), RequirementNode("m", "METRIC", "revenue")),
        edges=(),
    )
    predicted = RequirementGraph(
        nodes=(RequirementNode("e", "ENTITY", "AAPL"),),
        edges=(),
    )
    quality = graph_quality(predicted, gold)
    assert quality["node_precision"] == 1.0
    assert quality["node_recall"] == 0.5
    assert quality["node_f1"] == pytest.approx(2 / 3)
