"""Tests for the day-1 human-validation pilot scaffolding.

These tests exercise the MECHANICS (queue construction, hashing, reliability
math, pilot gating). Any labels in fixtures are clearly-marked synthetic test
values — never real human annotations.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from pathlib import Path

import pytest

from finvest.benchmark.schemas import EvidenceItem
from finvest.human_study.day1_pilot import (
    ANNOTATION_FIELDS,
    SIGNATURE_FIELDS,
    BASE_TICKERS,
    BLIND_REPEAT_SIZE,
    DAY1_DIR,
    FREEZE_SEED,
    INTERFACE_DISPLAY_CONDITIONS,
    INTERFACE_PER_CONDITION,
    PAIRED_CONDITIONS,
    PAIRED_PER_CONDITION,
    PILOT_MARKERS,
    build_base_queue,
    build_inference_features,
    build_interface_cases,
    build_paired_queue,
    canonical_json,
    cohen_kappa,
    compute_intra_rater,
    evidence_jaccard,
    freeze_day1,
    numeric_agreement,
    predict_coverage,
    run_vista_pilot,
    select_blind_repeat,
    sha256_hex,
    verify_frozen,
)
from finvest.human_study.day1_pilot import (
    LowCapacityLogistic,
    _evaluate_methods_on_cases,
)
from finvest.retrieval.full_corpus import FullCorpus


# ---------------------------------------------------------------------------
# Queue construction
# ---------------------------------------------------------------------------

def test_build_base_queue_is_22_and_deterministic() -> None:
    cases = build_base_queue()
    assert len(cases) == 22
    assert [c.case_id for c in cases] == [c.case_id for c in build_base_queue()]
    assert {c.issuer_id for c in cases} == set(BASE_TICKERS)


def test_paired_queue_stratified_12() -> None:
    cases = build_base_queue()
    paired = build_paired_queue(cases, seed=FREEZE_SEED)
    assert len(paired) == len(PAIRED_CONDITIONS) * PAIRED_PER_CONDITION == 12
    conditions = [i.condition for i in paired]
    for condition in PAIRED_CONDITIONS:
        assert conditions.count(condition) == PAIRED_PER_CONDITION, condition
    # Distinct (case, condition) pairs.
    pairs = [(i.base_case_id, i.condition) for i in paired]
    assert len(set(pairs)) == len(pairs)


def test_paired_queue_deterministic() -> None:
    cases = build_base_queue()
    a = build_paired_queue(cases, seed=FREEZE_SEED)
    b = build_paired_queue(cases, seed=FREEZE_SEED)
    assert [i.instance_id for i in a] == [i.instance_id for i in b]


def test_blind_repeat_selection() -> None:
    cases = build_base_queue()
    ids = {c.case_id for c in cases}
    selection = select_blind_repeat(cases, seed=FREEZE_SEED)
    assert len(selection) == BLIND_REPEAT_SIZE == 5
    assert [r["temp_id"] for r in selection] == [
        "br-01", "br-02", "br-03", "br-04", "br-05"
    ]
    chosen = {r["case_id"] for r in selection}
    assert chosen <= ids
    assert len(chosen) == BLIND_REPEAT_SIZE  # unique
    again = select_blind_repeat(cases, seed=FREEZE_SEED)
    assert selection == again


def test_interface_cases_9_distinct_balanced() -> None:
    cases = build_base_queue()
    interface = build_interface_cases(cases, seed=FREEZE_SEED)
    assert len(interface) == len(INTERFACE_DISPLAY_CONDITIONS) * INTERFACE_PER_CONDITION == 9
    questions = {i["base_question_id"] for i in interface}
    assert len(questions) == 9
    conditions = [i["display_condition"] for i in interface]
    for condition in INTERFACE_DISPLAY_CONDITIONS:
        assert conditions.count(condition) == INTERFACE_PER_CONDITION, condition
    # Every interface case carries a candidate display bundle (sealed).
    assert all("candidate_answer" in i for i in interface)


# ---------------------------------------------------------------------------
# Freeze + hash
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def frozen(tmp_path_factory: pytest.TempPathFactory) -> Path:
    day1 = tmp_path_factory.mktemp("day1_frozen")
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1)
    return Path(day1)


def test_freeze_writes_manifest_and_hashes(frozen: Path) -> None:
    day1 = frozen
    assert (day1 / "QUEUE_MANIFEST.json").exists()
    assert (day1 / "FROZEN.sha256").exists()
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"]["human_labels"] == "PENDING_HUMAN_LABEL"
    assert manifest["status"]["signed"] is False
    assert len(manifest["components"]) == 8  # 7 sealed + reviewer_view


def test_verify_frozen_no_violations(frozen: Path) -> None:
    day1 = frozen
    result = verify_frozen(day1_dir=day1)
    assert result["verified"] is True
    assert result["violations"] == []


def test_verify_frozen_detects_tampering(tmp_path: Path) -> None:
    freeze_day1(seed=FREEZE_SEED, day1_dir=tmp_path)
    manifest_path = tmp_path / "QUEUE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sealed"]["base_22_queue"][0]["question"] = "tampered question"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    result = verify_frozen(day1_dir=tmp_path)
    assert result["verified"] is False
    assert any("base_22_queue" in v for v in result["violations"])


def test_reviewer_view_has_no_candidate_labels(frozen: Path) -> None:
    day1 = frozen
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    reviewer = manifest["reviewer_view"]
    forbidden = {
        "gold_answer", "decision_label", "sufficiency_label",
        "acceptable_evidence_sets", "minimal_evidence_sets",
        "calculation_program", "known_conflicts", "answer_type",
    }
    for row in reviewer["base_22"]:
        assert not (set(row) & forbidden), row
    for row in reviewer["paired_12"]:
        assert "instance_id" not in row  # condition-embedding id hidden
        assert row["condition_identity"] == "HIDDEN_DURING_REVIEW"
    # Sealed content does carry the candidates (audit trail).
    sealed_questions = {
        c["question"] for c in manifest["sealed"]["base_22_queue"]
    }
    assert len(sealed_questions) == 22


def test_paired_token_map_resolves(frozen: Path) -> None:
    day1 = frozen
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    token_map = manifest["sealed"]["paired_12_token_map"]
    assert len(token_map) == 12
    assert all(token.startswith("pr-") for token in token_map)
    assert all("::" in instance_id for instance_id in token_map.values())


def test_empty_human_record_files_created(frozen: Path) -> None:
    day1 = frozen
    for name in (
        "BASE_22_HUMAN_SIGNED.jsonl",
        "PAIRED_12_HUMAN_SIGNED.jsonl",
        "BLIND_REPEAT_5.jsonl",
        "INTERFACE_PILOT_9.jsonl",
    ):
        assert (day1 / name).exists()
        assert (day1 / name).stat().st_size == 0


def test_hash_helpers_stable() -> None:
    assert sha256_hex(canonical_json({"b": 1, "a": [1, 2]})) == sha256_hex(
        canonical_json({"a": [1, 2], "b": 1})
    )
    assert sha256_hex("abc") == sha256_hex("abc")


# ---------------------------------------------------------------------------
# Reliability math (fixtures only — never real labels)
# ---------------------------------------------------------------------------

def test_cohen_kappa_perfect_and_mixed() -> None:
    perfect = cohen_kappa([("a", "a")] * 5)
    assert perfect["kappa"] == 1.0
    assert perfect["p0"] == 1.0
    assert "small_sample_warning" in perfect and perfect["small_sample_warning"]
    # Classic 2x2: 8/10 observed agreement, expected 0.5 -> kappa 0.6.
    mixed = cohen_kappa([("1", "1")] * 4 + [("0", "0")] * 4 + [("1", "0"), ("0", "1")])
    assert mixed["kappa"] == pytest.approx(0.6, abs=1e-4)
    assert mixed["p0"] == pytest.approx(0.8)


def test_evidence_jaccard_math() -> None:
    result = evidence_jaccard([{"a", "b"}, {"a"}], [{"a", "b"}, {"b", "c"}])
    assert result["mean_jaccard"] == pytest.approx(0.5)  # (1.0 + 0.0) / 2
    empty = evidence_jaccard([set()], [set()])
    assert empty["mean_jaccard"] == 1.0  # both empty -> agree by convention


def test_numeric_agreement() -> None:
    assert numeric_agreement(None, None) is True
    assert numeric_agreement(1.0, None) is False
    assert numeric_agreement(129.8, 129.8) is True
    assert numeric_agreement(129.8, 130.0, tolerance=1e-2) is True
    assert numeric_agreement(129.8, 130.0) is False


def test_compute_intra_rater_no_data() -> None:
    result = compute_intra_rater([])
    assert result["status"] == "NO_DATA"


def test_compute_intra_rater_fixture_pair() -> None:
    records = []
    for temp_id in ("br-01", "br-02", "br-03", "br-04", "br-05"):
        for pass_no, answer in ((1, 129.8), (2, 129.8)):
            records.append({
                "temp_id": temp_id, "pass": pass_no,
                "final_answer_or_null": answer,
                "entity": "AAPL", "target_period": "FY2024",
                "unit_and_scale": "USD", "supporting_evidence_ids": ["e1", "e2"],
            })
    result = compute_intra_rater(records)
    assert result["n_paired"] == 5
    assert result["categorical_agreement"] == 1.0
    assert result["cohens_kappa"]["kappa"] == 1.0
    assert result["evidence_set_jaccard"]["mean_jaccard"] == 1.0
    assert result["numeric_agreement"] == 1.0
    assert "EXPLORATORY_PILOT" in result["markers"]


# ---------------------------------------------------------------------------
# VISTA pilot gate
# ---------------------------------------------------------------------------

def _signed_record(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id, "signed": True, "signed_by": "fixture-researcher",
        "timestamp": "2026-08-06T00:00:00+00:00",
        "supporting_evidence_ids": [], "minimal_evidence_set": [],
    }


def test_vista_gate_insufficient_without_labels(frozen: Path) -> None:
    day1 = frozen
    out = day1 / "VISTA.json"
    payload = run_vista_pilot(day1_dir=day1, output_path=out)
    assert payload["status"] == "INSUFFICIENT_DATA_FOR_TRAINING"
    assert payload["human_verified_label_count"] == 0
    assert payload["result"] is None
    assert all(marker in payload["markers"] for marker in PILOT_MARKERS)
    assert out.exists()


def test_vista_gate_below_eligibility_threshold(
    frozen: Path, tmp_path: Path
) -> None:
    day1 = frozen
    (day1 / "BASE_22_HUMAN_SIGNED.jsonl").write_text(
        "\n".join(
            json.dumps(_signed_record(cid))
            for cid in ("finvest-AAPL-fcff-2024", "finvest-AAPL-fcff-2025",
                        "finvest-MSFT-fcff-2025")
        ) + "\n",
        encoding="utf-8",
    )
    payload = run_vista_pilot(day1_dir=day1, output_path=tmp_path / "VISTA.json")
    assert payload["status"] == "INSUFFICIENT_DATA_FOR_TRAINING"
    assert payload["human_verified_label_count"] == 3
    assert "required" in payload["reason"]


def test_unsigned_records_never_count(frozen: Path, tmp_path: Path) -> None:
    day1 = frozen
    rec = dict(_signed_record("finvest-AAPL-fcff-2024"))
    rec["signed"] = False
    rec["signed_by"] = None
    rec["timestamp"] = None
    (day1 / "BASE_22_HUMAN_SIGNED.jsonl").write_text(
        json.dumps(rec) + "\n", encoding="utf-8"
    )
    payload = run_vista_pilot(day1_dir=day1, output_path=tmp_path / "VISTA.json")
    assert payload["human_verified_label_count"] == 0


# ---------------------------------------------------------------------------
# P1 mechanics (fixtures only)
# ---------------------------------------------------------------------------

def test_low_capacity_logistic_converges() -> None:
    model = LowCapacityLogistic(seed=1)
    x = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [0.0, 1.0]]
    y = [1.0, 0.0, 1.0, 0.0]
    model.fit(x, y)
    assert model.predict_proba([1.0, 0.0]) > model.predict_proba([0.0, 1.0])
    # Deterministic given seed.
    model2 = LowCapacityLogistic(seed=1)
    model2.fit(x, y)
    assert model.weights == model2.weights


def test_predict_coverage_heuristics() -> None:
    nodes = [
        {"node_id": "ticker", "node_type": "ENTITY", "value": "AAPL"},
        {"node_id": "period", "node_type": "PERIOD", "value": "2024"},
        {"node_id": "ocf", "node_type": "INTERMEDIATE_VALUE", "value": "OpCF"},
    ]
    unit = EvidenceItem(
        evidence_id="e1", document_id="AAPL-10-K-2024-09-28",
        document_version="10-K", filing_date=date(2024, 11, 1),
        valid_from=date(2024, 9, 28), concept="OpCF", unit="USD", scale="1",
    )
    assert predict_coverage(unit, nodes) == frozenset({"ticker", "period", "ocf"})
    wrong_period = EvidenceItem(
        evidence_id="e2", document_id="AAPL-10-K-2023-09-30",
        document_version="10-K", filing_date=date(2023, 11, 1),
        valid_from=date(2023, 9, 30), concept="OpCF", unit="USD", scale="1",
    )
    assert predict_coverage(wrong_period, nodes) == frozenset({"ticker", "ocf"})


def test_inference_features_are_gold_free() -> None:
    features = build_inference_features(
        retrieval_score=1.5, coverage=frozenset({"a"}), total_requirements=2,
        temporal_flag=1.0, conflict_flag=0.0, execution_flag=1.0,
        unit_match_flag=1.0, period_overlap_flag=1.0, text_length=120.0,
    )
    assert len(features) == 8
    assert features[0] == 1.5
    assert features[1] == 0.5  # coverage fraction 1/2
    assert all(isinstance(f, float) for f in features)


def test_evaluate_methods_on_cases_fixture() -> None:
    """Deterministic end-to-end evaluation on a tiny synthetic corpus."""
    e1 = EvidenceItem(
        evidence_id="e1", document_id="FAKE-10-K-2024-12-31",
        document_version="10-K", filing_date=date(2025, 2, 1),
        valid_from=date(2024, 12, 31), concept="OpCF", unit="USD", scale="1",
        text_span="operating cash flow 100",
    )
    e2 = EvidenceItem(
        evidence_id="e2", document_id="FAKE-10-K-2023-12-31",
        document_version="10-K", filing_date=date(2024, 2, 1),
        valid_from=date(2023, 12, 31), concept="OpCF", unit="USD", scale="1",
        text_span="operating cash flow 80",
    )
    corpus = FullCorpus(
        units=(e1, e2),
        documents=("FAKE-10-K-2024-12-31", "FAKE-10-K-2023-12-31"),
        by_document={},
    )
    case: dict[str, Any] = {
        "case_id": "finvest-FAKE-fcff-2024",
        "question": "What is FAKE free cash flow to the firm for fiscal year 2024?",
        "source_cutoff": "2025-06-30T00:00:00",
        "target_period_end": "2024-12-31",
        "known_conflicts": [],
        "version_relations": [],
        "calculation_program": {"operation": "subtract", "inputs": ["OpCF"],
                                "result": 100.0},
        "requirement_graph": {"nodes": [
            {"node_id": "ticker", "node_type": "ENTITY", "value": "FAKE"},
            {"node_id": "period", "node_type": "PERIOD", "value": "2024"},
            {"node_id": "ocf", "node_type": "INTERMEDIATE_VALUE", "value": "OpCF"},
            {"node_id": "fcff", "node_type": "FINAL_VALUE", "value": None},
        ]},
    }
    gold: dict[str, Any] = {"case_id": case["case_id"],
                            "supporting_evidence_ids": ["e1"],
                            "minimal_evidence_set": ["e1"]}
    model = LowCapacityLogistic(seed=1)
    config: dict[str, Any] = {
        "baselines": ["b1_top_k", "b2_greedy_set_cover", "b3_beam_search",
                      "b4_ilp_oracle"],
        "_fitted_model": model,
    }
    records = _evaluate_methods_on_cases(
        [case], {case["case_id"]: gold}, corpus, seed=1, config=config,
    )
    assert len(records) == 1
    row = records[0]
    # B1 top-5 over 2 units picks both: recall 1.0, precision 0.5.
    assert row["b1_top_k"]["all_required_evidence_recall"] == 1.0
    assert row["b1_top_k"]["evidence_set_precision"] == 0.5
    # e2 is from the wrong period (2023 vs target 2024).
    assert row["b1_top_k"]["wrong_period_rate"] == 0.5
    # Oracle B4 picks exactly e1: precision 1.0, no wrong-period unit.
    assert row["b4_ilp_oracle"]["evidence_set_precision"] == 1.0
    assert row["b4_ilp_oracle"]["wrong_period_rate"] == 0.0
    # Greedy/beam cover requirements with e1 only.
    assert row["b2_greedy_set_cover"]["evidence_set_precision"] == 1.0
    assert row["b3_beam_search"]["evidence_set_precision"] == 1.0


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

def test_annotation_fields_complete() -> None:
    # Exactly the field list mandated by the day-1 pilot brief.
    required = {
        "question_valid", "answerability", "sufficiency", "entity", "metric",
        "target_period", "unit_and_scale", "reporting_scope",
        "mandatory_requirements", "supporting_evidence_ids", "minimal_evidence_set",
        "source_time_valid", "version_valid", "calculation_reproducible",
        "final_answer_or_null", "reviewer_confidence", "reviewer_notes",
        "signed_by", "timestamp", "elapsed_seconds",
    }
    assert set(ANNOTATION_FIELDS) == required
    assert set(SIGNATURE_FIELDS) == {"signed_by", "timestamp"}


def test_day1_dir_is_under_repo() -> None:
    assert DAY1_DIR.relative_to(Path(__file__).resolve().parents[2])
