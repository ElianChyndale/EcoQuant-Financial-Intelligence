"""Tests for the financial-ai-contracts adapter (Phase 5.1).

Skipped when the tool repo is not installed (CI installs only EcoQuant deps).
Asserts the adapter produces schema-valid records and stable canonical hashes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

financial_ai_contracts = pytest.importorskip("financial_ai_contracts")
from financial_ai_contracts.canonical import record_hash as fac_record_hash
from financial_ai_contracts.validation import validate_record

from integrations.contracts_adapter import (
    evidence_item_to_evidence_unit,
    experiment_output_to_experiment_record,
    finvest_case_to_benchmark_case,
    record_hash,
)


def _sample_case() -> dict:
    return {
        "case_id": "finvest-AAPL-cashflow-proxy-2024",
        "question": "What is AAPL operating cash flow minus capex for FY2024?",
        "answer_type": "derived",
        "issuer_id": "AAPL",
        "gold_answer": {"value": 108807000000.0, "unit": "USD"},
        "evidence_items": [
            {
                "evidence_id": "AAPL:us-gaap:NetCashProvidedByUsedInOperatingActivities:USD:2023-10-01:2024-09-28:10-K:0000320193-24-000123",
                "document_id": "AAPL-10-K-2024-09-28",
            },
            {
                "evidence_id": "AAPL:us-gaap:PaymentsToAcquirePropertyPlantAndEquipment:USD:2023-10-01:2024-09-28:10-K:0000320193-24-000123",
                "document_id": "AAPL-10-K-2024-09-28",
            },
        ],
    }


def test_case_to_benchmark_case_valid() -> None:
    case = _sample_case()
    bc = finvest_case_to_benchmark_case(case)
    assert bc.answerable is True
    assert bc.gold_answer is not None
    assert bc.gold_answer.currency == "USD"
    assert bc.question_type == "numerical"  # derived -> numerical
    assert bc.split == "test"
    assert bc.synthetic is True
    # Validates against JSON schema + semantic rules.
    validate_record(bc.model_dump(mode="json", by_alias=True), contract_type="benchmark-case")


def test_case_to_benchmark_case_abstain() -> None:
    case = _sample_case()
    case["gold_answer"] = None
    case["answer_type"] = "unanswerable"
    bc = finvest_case_to_benchmark_case(case)
    assert bc.answerable is False
    assert bc.abstention_expected is True
    assert bc.gold_answer is None
    validate_record(bc.model_dump(mode="json", by_alias=True), contract_type="benchmark-case")


def test_evidence_to_evidence_unit_valid() -> None:
    item = {
        "evidence_id": "AAPL:us-gaap:NetCashProvidedByUsedInOperatingActivities:USD:2023-10-01:2024-09-28:10-K:0000320193-24-000123",
        "document_id": "AAPL-10-K-2024-09-28",
        "concept": "NetCashProvidedByUsedInOperatingActivities",
        "val": 118254000000.0,
        "unit": "USD",
        "start": "2023-10-01",
        "end": "2024-09-28",
        "filed": "2024-11-01",
        "issuer": "AAPL",
    }
    eu = evidence_item_to_evidence_unit(item)
    assert eu.text
    assert eu.source_time.tzinfo is not None
    assert eu.valid_time.start.tzinfo is not None
    assert eu.document_hash.startswith("0x") and len(eu.document_hash) == 66
    validate_record(eu.model_dump(mode="json", by_alias=True), contract_type="evidence-unit")


def test_experiment_record_valid() -> None:
    output = {
        "n_cases": 19,
        "decisions": {"ANSWER": 0, "REVIEW": 19, "ABSTAIN": 0},
        "answer_agreement": {"rate": 0.0},
        "corpus": {"corpus_id": "abc123"},
        "markers": ["SOLO_PROVISIONAL", "NOT_PAPER_HEADLINE"],
    }
    rec = experiment_output_to_experiment_record(
        output, experiment_id="a11-two-stage", seed=42,
        commit="7c1bf11000000000000000000000000000000000",
    )
    assert len(rec.metrics) >= 5
    assert rec.seed == 42
    assert rec.environment.dependency_lock_hash.startswith("0x")
    validate_record(rec.model_dump(mode="json", by_alias=True), contract_type="experiment-record")


def test_canonical_hash_stable() -> None:
    """record_hash is stable across dict ordering (canonical JSON)."""
    case = _sample_case()
    bc1 = finvest_case_to_benchmark_case(case)
    dump1 = bc1.model_dump(mode="json", by_alias=True)
    # Re-dump in a different key order — canonical JSON must still match.
    reordered = {k: dump1[k] for k in sorted(dump1, reverse=True)}
    assert fac_record_hash(reordered) == fac_record_hash(dump1)
    assert record_hash(bc1) == fac_record_hash(dump1)


def test_identifiers_lowercase() -> None:
    """FAC identifiers must be lowercase (FinVEST ids are uppercase)."""
    case = _sample_case()
    bc = finvest_case_to_benchmark_case(case)
    assert bc.case_id == bc.case_id.lower()
    for eid in bc.gold_evidence_ids:
        assert eid == eid.lower()
    assert bc.case_id == "finvest-aapl-cashflow-proxy-2024"
