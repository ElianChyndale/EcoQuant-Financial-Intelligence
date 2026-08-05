from __future__ import annotations

import pytest

from finvest.set_selection.selectors import (
    CoverageModel,
    b1_top_k,
    b2_greedy_set_cover,
    b3_beam_search,
    b4_ilp_oracle,
    set_metrics,
    vista_fin_selector,
)
from finvest.benchmark.schemas import RequirementEdge, RequirementGraph, RequirementNode


@pytest.fixture
def coverage() -> CoverageModel:
    # ev-a covers entity+metric, ev-b covers period, ev-c covers none.
    return CoverageModel({
        "ev-a": frozenset({"entity", "metric"}),
        "ev-b": frozenset({"period"}),
        "ev-c": frozenset(),
    })


def test_b1_top_k_no_requirement_awareness() -> None:
    selected = b1_top_k(("ev-a", "ev-b", "ev-c"), k=2)
    assert selected.evidence_ids == ("ev-a", "ev-b")
    assert selected.method == "b1_top_k"


def test_b2_greedy_set_cover(coverage) -> None:
    selected = b2_greedy_set_cover(
        ("ev-a", "ev-b", "ev-c"),
        frozenset({"entity", "metric", "period"}),
        coverage,
    )
    # ev-a covers 2 requirements, ev-b covers the last.
    assert set(selected.evidence_ids) == {"ev-a", "ev-b"}
    assert selected.covered_requirements == frozenset({"entity", "metric", "period"})


def test_b2_stops_when_uncovered_requirements_remain(coverage) -> None:
    selected = b2_greedy_set_cover(
        ("ev-a", "ev-c"),
        frozenset({"entity", "metric", "period", "scope"}),
        coverage,
    )
    # ev-c covers nothing; scope never covered.
    assert "scope" not in selected.covered_requirements


def test_b3_beam_search_finds_cover(coverage) -> None:
    selected = b3_beam_search(
        ("ev-a", "ev-b", "ev-c"),
        frozenset({"entity", "metric", "period"}),
        coverage,
    )
    assert selected.covered_requirements == frozenset({"entity", "metric", "period"})


def test_b4_ilp_oracle_uses_gold(coverage) -> None:
    selected = b4_ilp_oracle(
        ("ev-a", "ev-b", "ev-c"),
        frozenset({"entity", "metric", "period"}),
        coverage,
    )
    assert selected.is_oracle is True
    assert selected.covered_requirements == frozenset({"entity", "metric", "period"})


def test_vista_fin_selector_preserves_interface() -> None:
    graph = RequirementGraph(
        nodes=(
            RequirementNode("entity", "ENTITY", "AAPL"),
            RequirementNode("metric", "METRIC", "revenue"),
            RequirementNode("period", "PERIOD", "FY2024"),
        ),
        edges=(RequirementEdge("metric", "entity", "SAME_AS"),),
    )
    coverage = CoverageModel({
        "ev-a": frozenset({"entity", "metric"}),
        "ev-b": frozenset({"period"}),
    })
    selected = vista_fin_selector(("ev-a", "ev-b"), graph, coverage)
    assert set(selected.evidence_ids) == {"ev-a", "ev-b"}


def test_set_metrics() -> None:
    selected = b1_top_k(("ev-a", "ev-b"), k=2)
    metrics = set_metrics(
        selected,
        gold_evidence=frozenset({"ev-a", "ev-b"}),
        gold_minimal=frozenset({"ev-a"}),
        requirements=frozenset({"entity", "metric", "period"}),
        coverage=CoverageModel({
            "ev-a": frozenset({"entity", "metric"}),
            "ev-b": frozenset({"period"}),
        }),
    )
    assert metrics["set_exact_match"] == 1.0
    assert metrics["all_required_evidence_recall"] == 1.0
    assert metrics["minimal_set_recall"] == 1.0
    assert metrics["set_precision"] == 1.0
