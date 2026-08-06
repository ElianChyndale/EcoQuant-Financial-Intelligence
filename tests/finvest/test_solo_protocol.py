"""Tests for the solo provisional annotation protocol (Phase 13).

Proves: status lifecycle, Q2->sufficiency mapping, append-only records,
machine verification AFTER submission, risk layering (Green/Yellow/Red),
and that human raw choices are kept separate from derived labels.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1
from finvest.human_study.protocol_config import V0_2_DRAFT
from finvest.human_study.solo_protocol import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    EVIDENCE_CONFLICTING,
    EVIDENCE_ENOUGH,
    EVIDENCE_NOT_ENOUGH,
    EVIDENCE_PARTLY,
    Q1_AMBIGUOUS,
    Q1_CLEAR,
    Q1_INVALID,
    ROUTE_ABSTAIN,
    ROUTE_ANSWER,
    ROUTE_REVIEW,
    STATUS_NEEDS_EXTERNAL,
    STATUS_SOLO_PROVISIONAL,
    SUFFICIENCY_MAP,
    confidence_from_legacy,
    status_for_route,
)
from finvest.human_study.solo_records import (
    SoloAnnotation,
    append_annotation,
    derive_labels,
    latest_annotation,
    load_annotations,
)
from finvest.human_study.solo_verification import (
    render_diff_report,
    verify_annotation,
)
from finvest.human_study.web.services.case_presenter import (
    base_cases,
    load_manifest,
    present_from_manifest,
)


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    """Frozen v0.2-draft manifest + fixture cache (like the workbench)."""
    tmp = tmp_path_factory.mktemp("solo")
    cache = tmp / "cache"
    sec = cache / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
        encoding="utf-8"
    )
    for ticker in ("aapl", "msft", "ko", "eqix", "jnj", "ups"):
        (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")
    day1 = tmp / "day1"
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1, min_cases=1, cache_dir=cache,
                protocol=V0_2_DRAFT)
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    return manifest, cache


# --- Mapping rules ---

def test_q2_to_sufficiency_mapping() -> None:
    assert SUFFICIENCY_MAP[EVIDENCE_ENOUGH] == "SUPPORTED"
    assert SUFFICIENCY_MAP[EVIDENCE_PARTLY] == "PARTIAL"
    assert SUFFICIENCY_MAP[EVIDENCE_CONFLICTING] == "CONFLICTING"
    assert SUFFICIENCY_MAP[EVIDENCE_NOT_ENOUGH] == "INSUFFICIENT"


def test_derive_labels_keeps_raw_separate() -> None:
    d = derive_labels(Q1_CLEAR, EVIDENCE_ENOUGH, issue_flags=(), route=ROUTE_ANSWER)
    assert d["question_valid"] == "VALID"
    assert d["answerability"] == "ANSWERABLE"
    assert d["sufficiency"] == "SUPPORTED"
    assert d["route"] == "ANSWER"
    # Raw human choices are NOT the derived labels.
    assert d["question_valid"] != Q1_CLEAR  # human chose CLEAR, system says VALID


def test_derive_labels_calc_mismatch_downgrades_route() -> None:
    d = derive_labels(Q1_CLEAR, EVIDENCE_ENOUGH, issue_flags=(), route=ROUTE_ANSWER,
                      calc_mismatch=True)
    assert d["route"] == "REVIEW"
    assert d["calculation_reproducible"] is False


def test_confidence_legacy_mapping() -> None:
    assert confidence_from_legacy(5) == CONFIDENCE_HIGH
    assert confidence_from_legacy(4) == CONFIDENCE_HIGH
    assert confidence_from_legacy(3) == CONFIDENCE_MEDIUM
    assert confidence_from_legacy(2) == CONFIDENCE_LOW
    assert confidence_from_legacy(1) == CONFIDENCE_LOW
    assert confidence_from_legacy(None) is None


# --- Risk layering (Stage 4) ---

def test_status_green_answer_high() -> None:
    assert status_for_route(ROUTE_ANSWER, CONFIDENCE_HIGH) == STATUS_SOLO_PROVISIONAL


def test_status_red_review() -> None:
    assert status_for_route(ROUTE_REVIEW, CONFIDENCE_HIGH) == STATUS_NEEDS_EXTERNAL


def test_status_red_hard_issue() -> None:
    assert status_for_route(ROUTE_ANSWER, CONFIDENCE_HIGH,
                            issue_flags=("WRONG_PERIOD",)) == STATUS_NEEDS_EXTERNAL


def test_status_yellow_soft_issue_provisional() -> None:
    assert status_for_route(ROUTE_ANSWER, CONFIDENCE_HIGH,
                            issue_flags=("FUTURE_SOURCE",)) == STATUS_SOLO_PROVISIONAL


def test_status_red_abstain() -> None:
    assert status_for_route(ROUTE_ABSTAIN, CONFIDENCE_LOW) == STATUS_NEEDS_EXTERNAL


# --- Append-only records ---

def test_append_only_and_latest(tmp_path: Path) -> None:
    path = tmp_path / "SOLO.jsonl"
    a1 = SoloAnnotation(
        case_id="c1", evidence_package_version="1.0", evidence_package_hash="h1",
        annotation_protocol_version="solo-v1", reviewer_id="R1", annotation_round=1,
        question_clarity=Q1_CLEAR, evidence_judgement=EVIDENCE_ENOUGH,
        selected_evidence_ids=("E1",), human_inputs={"E1": 1},
        human_answer="1", issue_flags=("NO_ISSUE",), route=ROUTE_ANSWER,
        confidence=CONFIDENCE_HIGH, rationale="ok", duration_seconds=10,
    )
    append_annotation(path, a1)
    # Second round for the same case appends, never overwrites.
    a2 = SoloAnnotation(
        case_id="c1", evidence_package_version="1.0", evidence_package_hash="h1",
        annotation_protocol_version="solo-v1", reviewer_id="R1", annotation_round=2,
        question_clarity=Q1_CLEAR, evidence_judgement=EVIDENCE_ENOUGH,
        selected_evidence_ids=("E1",), human_inputs={"E1": 1},
        human_answer="1", issue_flags=("NO_ISSUE",), route=ROUTE_ANSWER,
        confidence=CONFIDENCE_HIGH, rationale="ok", duration_seconds=9,
    )
    append_annotation(path, a2)
    recs = load_annotations(path)
    assert len(recs) == 2
    assert latest_annotation(path, "c1")["annotation_round"] == 2
    assert recs[0]["annotation_round"] == 1  # preserved


# --- Machine verification (Stage 3) ---

def test_verification_matches(env) -> None:
    manifest, cache = env
    case = next(c for c in base_cases(manifest) if "cashflow-proxy" in c["case_id"])
    p = present_from_manifest(cache.parent / "day1", cache, case["case_id"])
    rows = p["raw_rows"]
    # Machine calc: OCF - capex (fixture values 118e9 - 11e9 = 107e9).
    correct = "107000000000"
    result = verify_annotation(
        raw_rows=rows,
        human_answer=correct,
        human_route="ANSWER",
        source_cutoff=str(p["time_version"]["source_cutoff"] or ""),
        target_period_end=str(p["time_version"]["target_period"]),
        displayed_values={r["concept"]: r["val"] for r in rows},
    )
    assert result.calc_match is True
    assert "period_mismatch" not in result.mismatches
    assert "calculation_mismatch" not in result.mismatches


def test_verification_detects_calc_mismatch(env) -> None:
    manifest, cache = env
    case = next(c for c in base_cases(manifest) if "cashflow-proxy" in c["case_id"])
    p = present_from_manifest(cache.parent / "day1", cache, case["case_id"])
    rows = p["raw_rows"]
    result = verify_annotation(
        raw_rows=rows, human_answer="999999999999", human_route="ANSWER",
        source_cutoff=str(p["time_version"]["source_cutoff"] or ""),
        target_period_end=str(p["time_version"]["target_period"]),
    )
    assert result.calc_match is False
    assert "calculation_mismatch" in result.mismatches
    assert "MISMATCH" in render_diff_report(result)


def test_verification_period_label_tolerance() -> None:
    """FY2024 label must not trigger a mismatch against fact end 2024-09-28."""
    rows = [{"concept": "X", "val": 1, "accn": "a", "source_hash": "h",
             "start": "2023-10-01", "end": "2024-09-28", "filed": "2024-11-01",
             "form": "10-K", "unit": "USD", "issuer": "AAPL"}]
    result = verify_annotation(raw_rows=rows, human_answer=None, human_route="ANSWER",
                               source_cutoff="2024-11-01", target_period_end="FY2024")
    assert "period_mismatch" not in result.mismatches


# --- Delayed re-check (Stage 5) ---

def test_compare_rounds_confirmed(tmp_path: Path) -> None:
    from finvest.human_study.solo_records import compare_rounds

    r1 = {"case_id": "c1", "human_answer": "100", "route": "ANSWER",
          "question_clarity": Q1_CLEAR, "evidence_judgement": EVIDENCE_ENOUGH,
          "derived": {"sufficiency": "SUPPORTED"}}
    r2 = dict(r1)  # identical -> confirmed
    out = compare_rounds(r1, r2)
    assert out["status"] == "SOLO_CONFIRMED"
    assert out["numeric_agreement"] is True and out["route_agreement"] is True


def test_compare_rounds_numeric_disagreement(tmp_path: Path) -> None:
    from finvest.human_study.solo_records import compare_rounds

    r1 = {"case_id": "c1", "human_answer": "100", "route": "ANSWER",
          "question_clarity": Q1_CLEAR, "evidence_judgement": EVIDENCE_ENOUGH,
          "derived": {"sufficiency": "SUPPORTED"}}
    r2 = dict(r1); r2["human_answer"] = "999"
    out = compare_rounds(r1, r2)
    assert out["status"] == "NEEDS_EXTERNAL_REVIEW"


def test_recheck_case_needs_two_rounds(tmp_path: Path) -> None:
    from finvest.human_study.solo_records import append_annotation, recheck_case, SoloAnnotation

    path = tmp_path / "SOLO.jsonl"
    a = SoloAnnotation(
        case_id="c1", evidence_package_version="1.0", evidence_package_hash="h",
        annotation_protocol_version="solo-v1", reviewer_id="ELIAN_PRIMARY", annotation_round=1,
        question_clarity=Q1_CLEAR, evidence_judgement=EVIDENCE_ENOUGH,
        selected_evidence_ids=("E1",), human_inputs={"E1": 1},
        human_answer="100", issue_flags=("NO_ISSUE",), route=ROUTE_ANSWER,
        confidence=CONFIDENCE_HIGH, rationale="", duration_seconds=5,
    )
    append_annotation(path, a)
    assert recheck_case(path, "c1") is None  # only 1 round
    append_annotation(path, a)  # round 2 (identical)
    out = recheck_case(path, "c1")
    assert out is not None and out["status"] == "SOLO_CONFIRMED"


# --- Minimal experiments harness (runs, honest about leakage) ---

def test_minimal_experiments_harness_runs(tmp_path: Path) -> None:
    """The pilot harness must run and flag its own leakage honestly."""
    import subprocess, sys

    script = Path(__file__).resolve().parents[2] / "experiments/a10_integration/minimal_experiments.py"
    if not script.exists():
        pytest.skip("minimal_experiments script not present")
    r = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["n_annotated"] >= 20
    assert "leakage_warning" in out  # honest about the pilot's leakage
    assert out["coverage_curve"]["coverage_pct"] > 0
