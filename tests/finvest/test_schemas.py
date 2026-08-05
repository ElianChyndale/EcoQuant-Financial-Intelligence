from __future__ import annotations

from datetime import date, datetime

import pytest

from finvest.benchmark.schemas import (
    CalculationProgram,
    EvidenceItem,
    FinVESTCase,
    RequirementEdge,
    RequirementGraph,
    RequirementNode,
    VersionRelation,
)


def _valid_case() -> FinVESTCase:
    graph = RequirementGraph(
        nodes=(
            RequirementNode("fcff", "FINAL_VALUE"),
            RequirementNode("ocf", "INTERMEDIATE_VALUE", "OperatingCashFlow"),
            RequirementNode("capex", "INTERMEDIATE_VALUE", "CapitalExpenditure"),
        ),
        edges=(
            RequirementEdge("fcff", "ocf", "DERIVES_FROM"),
            RequirementEdge("fcff", "capex", "DERIVES_FROM"),
        ),
    )
    ev_a = EvidenceItem(
        evidence_id="ev-ocf", document_id="doc-1", document_version="10-K",
        filing_date=date(2025, 3, 1), concept="NetCashProvidedByUsedInOperatingActivities",
    )
    ev_b = EvidenceItem(
        evidence_id="ev-capex", document_id="doc-1", document_version="10-K",
        filing_date=date(2025, 3, 1), concept="PaymentsToAcquirePropertyPlantAndEquipment",
    )
    program = CalculationProgram(
        operation="subtract", inputs=("OperatingCashFlow", "CapitalExpenditure"),
        result=8.8e9, unit="USD", scale="1", period="FY2025",
    )
    return FinVESTCase(
        case_id="case-1", base_question_id="bq-1", issuer_id="AAPL",
        jurisdiction="US", question="What is Apple FCFF for FY2025?",
        source_cutoff=datetime(2025, 12, 31),
        target_period_start=date(2024, 10, 1), target_period_end=date(2025, 9, 30),
        target_fiscal_year="FY2025", answer_type="derived",
        gold_answer={"value": 8.8e9}, decision_label="ANSWER",
        sufficiency_label="SUPPORTED", requirement_graph=graph,
        acceptable_evidence_sets=(frozenset({"ev-ocf", "ev-capex"}),),
        minimal_evidence_sets=(frozenset({"ev-ocf", "ev-capex"}),),
        evidence_items=(ev_a, ev_b), calculation_program=program,
        version_relations=(VersionRelation("doc-1", "doc-1a", "AMENDS"),),
    )


def test_valid_case_passes() -> None:
    case = _valid_case()
    case.validate()  # no raise


def test_invalid_decision_label() -> None:
    case = _valid_case()
    with pytest.raises(ValueError, match="decision_label"):
        FinVESTCase(
            **{**case.__dict__, "decision_label": "INVALID"},
        ).validate()


def test_evidence_set_unknown_item() -> None:
    case = _valid_case()
    bad = FinVESTCase(
        **{**case.__dict__, "acceptable_evidence_sets": (frozenset({"ev-missing"}),)},
    )
    with pytest.raises(ValueError, match="unknown"):
        bad.validate()


def test_requirement_graph_validates() -> None:
    graph = RequirementGraph(
        nodes=(RequirementNode("a", "ENTITY"),),
        edges=(RequirementEdge("a", "b", "REQUIRES"),),  # b missing
    )
    with pytest.raises(ValueError, match="unknown node"):
        graph.validate()
