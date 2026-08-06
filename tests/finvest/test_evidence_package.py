"""Tests for the Self-Contained Human Evidence Package (Phase 11).

The acceptance criterion: a researcher must be able to judge a case from a
single page. These tests prove the package contains human-readable evidence
(not just XBRL tags), separate calculation inputs WITHOUT the candidate
result, a time & version card, machine fields only in the technical layer,
and that the package gate blocks unsettled-definition / empty-evidence cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1
from finvest.human_study.web.services.evidence_package import (
    build_evidence_package,
    package_gate,
)
from finvest.human_study.web.services.evidence_service import resolve_evidence_set
from finvest.human_study.web.services.human_readable import (
    format_value,
    human_label,
    unit_label,
)


@pytest.fixture(scope="module")
def fixture_env(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    """Frozen day-1 manifest + fixture cache (same shape as the workbench)."""
    tmp = tmp_path_factory.mktemp("shep")
    cache = tmp / "cache"
    sec = cache / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
        encoding="utf-8"
    )
    for ticker in ("aapl", "msft", "ko", "eqix", "jnj", "ups"):
        (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")
    day1 = tmp / "day1"
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1, min_cases=1, cache_dir=cache)
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    return manifest, cache


def _first_evidence_case(manifest) -> dict:
    return next(
        c for c in manifest["sealed"]["base_22_queue"] if c["evidence_items"]
    )


def _package_for(manifest, cache, case) -> dict:
    view = {
        "case_id": case["case_id"],
        "question": case["question"],
        "issuer": case["issuer_id"],
        "source_cutoff": case["source_cutoff"],
        "target_period": case["target_fiscal_year"],
        "evidence": case["evidence_items"],
    }
    resolved = resolve_evidence_set(view["evidence"], cache)
    return build_evidence_package(view, resolved, sealed_case=case)


def test_package_has_human_readable_evidence_table(fixture_env) -> None:
    manifest, cache = fixture_env
    pkg = _package_for(manifest, cache, _first_evidence_case(manifest))
    rows = pkg["evidence_table"]["rows"]
    assert rows, "evidence table must have rows"
    for row in rows:
        # Human-readable label: never the raw XBRL tag when a label exists.
        assert row["label"] != row["concept"] or row["label"] == human_label(row["concept"])
        assert row["value"] and row["unit"]
        assert row["filing_date"] and row["form"]


def test_human_labels_are_readable() -> None:
    assert human_label("NetCashProvidedByUsedInOperatingActivities") == \
        "Net cash provided by operating activities"
    assert human_label("PaymentsToAcquirePropertyPlantAndEquipment") == \
        "Payments for acquisition of property, plant and equipment"
    assert human_label("NoSuchConcept") == "NoSuchConcept"  # no silent rename
    assert unit_label("USD") == "USD"
    assert format_value(118_000_000_000) == "118,000,000,000"


def test_calculation_inputs_shown_separately_result_sealed(fixture_env) -> None:
    """Inputs are visible; the candidate RESULT must NEVER be in the package."""
    manifest, cache = fixture_env
    case = next(c for c in manifest["sealed"]["base_22_queue"]
                if "cashflow-proxy" in c["case_id"])
    pkg = _package_for(manifest, cache, case)
    calc = pkg["calculation"]
    assert calc["has_calculation"] is True
    assert len(calc["inputs"]) == 2  # OCF and capex shown separately
    labels = {i["label"] for i in calc["inputs"]}
    assert "Net cash provided by operating activities" in labels
    assert "Payments for acquisition of property, plant and equipment" in labels
    # The sealed candidate result must NOT leak into the display package.
    assert "result" not in calc
    assert "gold_answer" not in json.dumps(pkg)


def test_time_version_card_has_after_target_flag(fixture_env) -> None:
    manifest, cache = fixture_env
    pkg = _package_for(manifest, cache, _first_evidence_case(manifest))
    tv = pkg["time_version"]
    assert tv["target_period"]
    assert tv["source_cutoff"]
    for row in tv["rows"]:
        assert "filing_date" in row
        assert "after_target" in row  # True/False/None, never missing


def test_machine_fields_only_in_technical_layer(fixture_env) -> None:
    manifest, cache = fixture_env
    pkg = _package_for(manifest, cache, _first_evidence_case(manifest))
    assert pkg["machine"], "machine (technical) fields present"
    m = pkg["machine"][0]
    assert m["evidence_id"] and m["concept"] and m["accession"]
    # The machine fields are separate from the human table.
    for row in pkg["evidence_table"]["rows"]:
        assert "evidence_id" not in row


def test_gate_blocks_empty_evidence() -> None:
    pkg = {
        "definition": {"contested": False},
        "evidence_table": {"rows": []},
        "calculation": {"has_calculation": True, "inputs": []},
    }
    gate = package_gate(pkg)
    assert gate.signable is False
    assert "no_human_readable_evidence" in gate.reasons
    assert "calculation_inputs_missing" in gate.reasons


def test_gate_blocks_unsettled_definition() -> None:
    pkg = {
        "definition": {"contested": True},
        "evidence_table": {"rows": [{"x": 1}]},
        "calculation": {"has_calculation": False, "inputs": []},
    }
    gate = package_gate(pkg)
    assert gate.signable is False
    assert "definition_unsettled" in gate.reasons


def test_reference_sheet_is_human_readable_and_no_prefilled_answer(fixture_env, tmp_path) -> None:
    """The candidate sheet must NOT present the machine decision as the answer."""
    from finvest.benchmark.builders.sec_cases import build_sec_cases
    from finvest.human_study.reference_sheets import build_reference_sheet

    manifest, cache = fixture_env
    built = build_sec_cases(cache, tickers=("AAPL", "MSFT", "KO"), fixture=True)
    case = next(c for c in built.cases if len(c.evidence_items) >= 2)
    sheet = build_reference_sheet(case, cache_dir=cache, ticker=case.issuer_id)
    pkg = sheet["package"]
    assert pkg["evidence_table"]["rows"], "sheet evidence must be readable"
    # The machine candidate is clearly labelled, never presented as final.
    cand = sheet["machine_candidate"]
    assert "候选" in cand["note"]
    assert cand["decision"] is not None
    # The researcher review fields are NOT pre-filled.
    for key, val in sheet["researcher_review_fields"].items():
        assert val is None, f"review field {key} must start empty"


def test_practice_reveal_after_submit(fixture_env) -> None:
    """The practice reference is only produced at POST time (after judgement)."""
    manifest, cache = fixture_env
    from finvest.human_study.web.app import _practice_reference

    case = _first_evidence_case(manifest)
    ref = _practice_reference(manifest, case["case_id"])
    assert "机器候选" in ref["reference_answer"]
    assert ref["source_explanation"]
