from __future__ import annotations

from pathlib import Path

import pytest

from finvest.benchmark.builders.sec_cases import build_sec_cases
from finvest.benchmark.conditions import generate_conditions
from finvest.benchmark.schemas import EVIDENCE_CONDITIONS

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache"


@pytest.fixture(scope="module")
def built():
    return build_sec_cases(CACHE, tickers=("AAPL", "MSFT", "KO"))


def test_builder_produces_cases(built) -> None:
    assert len(built.cases) > 10
    assert built.cases[0].case_id
    assert built.cases[0].validate() is None  # no raise


def test_builder_has_derived_and_insufficient(built) -> None:
    types = {c.answer_type for c in built.cases}
    assert "derived" in types
    assert "unanswerable" in types


def test_fcff_case_has_program(built) -> None:
    derived = [c for c in built.cases if c.answer_type == "derived"]
    assert derived
    fcff = [c for c in derived if "fcff" in c.case_id]
    assert fcff
    case = fcff[0]
    assert case.calculation_program is not None
    assert case.calculation_program.operation == "subtract"
    assert case.requirement_graph is not None
    assert len(case.minimal_evidence_sets) >= 1


def test_amended_case_has_version_relation(built) -> None:
    amended = [c for c in built.cases if c.version_relations]
    assert amended
    case = amended[0]
    assert case.version_relations[0].relation == "AMENDS"
    assert case.sufficiency_label == "CONFLICTING"


def test_conditions_generate_paired_instances(built) -> None:
    case = built.cases[0]
    instances = generate_conditions(case)
    conditions = {i.condition for i in instances}
    # FULL + the conditions that apply to this case.
    assert "FULL" in conditions
    assert len(instances) >= 3
    for instance in instances:
        assert instance.instance_id.startswith(case.case_id)
        assert instance.question == case.question  # question fixed across conditions


def test_conditions_cover_financial_specifics(built) -> None:
    case = built.cases[0]
    instances = generate_conditions(case)
    condition_set = {i.condition for i in instances}
    # At least the financially-relevant conditions are generated for a case
    # with ≥2 evidence items.
    assert "PARTIAL_MISSING_INPUT" in condition_set
    assert "WRONG_PERIOD" in condition_set
    assert "CONFLICTING" in condition_set
