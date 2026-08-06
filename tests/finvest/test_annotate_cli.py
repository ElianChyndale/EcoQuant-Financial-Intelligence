"""Tests for the strictly neutral, human-controlled annotation CLI.

All "labels" in these tests are clearly-marked synthetic fixture inputs —
never real human annotations. The proofs requested by the brief:

1. candidate labels cannot appear in annotation output;
2. model scores cannot appear;
3. unsigned drafts are not counted as human labels;
4. records cannot be auto-signed;
5. invalid evidence IDs are rejected;
6. enum errors are rejected;
7. signed records cannot be overwritten;
8. resume skips signed cases;
9. blind pass refuses to run before the required waiting period;
10. blind pass cannot access pass-1 fields;
11. queue manifest and queue hashes remain unchanged;
12. Ctrl+C-safe draft persistence works.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from finvest.human_study.annotate_cli import (
    AnnotateOptions,
    BASE_FIELD_SPECS,
    CliError,
    FORBIDDEN_DISPLAY_KEYS,
    INTERFACE_FIELD_SPECS,
    draft_path,
    load_records,
    project_case,
    record_file,
    run_annotate,
    run_correct,
    run_review_draft,
    run_sign,
    run_status,
)
from finvest.human_study.day1_pilot import (
    FREEZE_SEED,
    canonical_json,
    freeze_day1,
    run_vista_pilot,
    sha256_hex,
    verify_frozen,
)

BASE_ORDER = [spec.name for spec in BASE_FIELD_SPECS]
INTERFACE_ORDER = [spec.name for spec in INTERFACE_FIELD_SPECS]


class FakeIO:
    """Injected stdin/stdout; KeyboardInterrupt when inputs run out (Ctrl+C)."""

    def __init__(self, inputs: list[str] | None = None) -> None:
        self._inputs = list(inputs or [])
        self.out: list[str] = []

    def print(self, text: str = "") -> None:
        self.out.append(str(text))

    def input(self, prompt: str = "") -> str:
        self.out.append(prompt)
        if not self._inputs:
            raise KeyboardInterrupt()
        return self._inputs.pop(0)


@pytest.fixture()
def env(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    day1 = tmp_path / "day1"
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1, min_cases=1)
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    return day1, manifest


def field_inputs(ids: list[str], *, values: dict[str, str] | None = None) -> list[str]:
    """Literal fixture inputs for the 18 base annotation fields."""
    support = " ".join(ids)
    fields = [
        "VALID", "ANSWERABLE", "SUPPORTED", "AAPL", "FCFF", "FY2024", "USD",
        "consolidated", "ENTITY PERIOD OCF", support, support, "true", "true",
        "true", "100", "4", "fixture notes", "",
    ]
    if values:
        for key, value in values.items():
            fields[BASE_ORDER.index(key)] = value
    return fields


def interface_inputs(values: dict[str, str] | None = None) -> list[str]:
    fields = ["ACCEPT", "true", "false", "false", "", "4", "fixture notes", ""]
    if values:
        for key, value in values.items():
            fields[INTERFACE_ORDER.index(key)] = value
    return fields


def case_of(manifest: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(
        c for c in manifest["sealed"]["base_22_queue"] if c["case_id"] == case_id
    )


def case_ids(manifest: dict[str, Any]) -> list[str]:
    """Case IDs in the SANCTIONED display order (reviewer_view), which is what
    the annotation CLI processes — not the sealed queue order."""
    return [r["case_id"] for r in manifest["reviewer_view"]["base_22"]]


def seed_base_signed(
    day1: Path, manifest: dict[str, Any], *, hours_ago: float, notes: str | None = None
) -> None:
    """Fixture: mark all base cases signed (timestamps only — not labels)."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(
        timespec="seconds"
    )
    lines = []
    for case_id in case_ids(manifest):
        record = {
            "record_type": "BASE_22", "case_id": case_id,
            "signed": True, "signed_by": "fixture", "timestamp": ts,
        }
        if notes is not None:
            record["reviewer_notes"] = notes
        lines.append(json.dumps(record, sort_keys=True))
    record_file(day1, "base").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Candidate labels cannot appear in annotation output
# ---------------------------------------------------------------------------

def test_annotation_display_has_no_candidate_labels(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    io = FakeIO(field_inputs(ids) + [f"SIGN {case['case_id']}"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    text = "\n".join(io.out)
    for token in FORBIDDEN_DISPLAY_KEYS:
        assert token not in text, token


def test_projection_excludes_forbidden_keys(
    env: tuple[Path, dict[str, Any]],
) -> None:
    _, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    projected = project_case(case)
    assert set(projected) <= {
        "case_id", "question", "issuer", "source_cutoff", "target_period",
        "evidence", "source_files",
    }
    assert not (set(projected) & set(FORBIDDEN_DISPLAY_KEYS))


# ---------------------------------------------------------------------------
# 2. Model scores cannot appear
# ---------------------------------------------------------------------------

def test_annotation_display_has_no_model_scores(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    io = FakeIO(field_inputs(ids) + [f"SIGN {case['case_id']}"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    text = "\n".join(io.out).lower()
    assert "score" not in text
    assert "prediction" not in text
    assert "probability" not in text


# ---------------------------------------------------------------------------
# 3. Unsigned drafts are not counted as human labels
# ---------------------------------------------------------------------------

def test_unsigned_drafts_not_counted(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    io = FakeIO(field_inputs(ids) + ["SKIP"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    assert load_records(record_file(day1, "base")) == []
    status_io = FakeIO([])
    run_status(manifest, status_io, day1_dir=day1)
    text = "\n".join(status_io.out)
    assert "base signed:            0 / 22" in text
    assert "unsigned drafts:        1" in text
    # The VISTA gate counts only signed records.
    payload = run_vista_pilot(day1_dir=day1, output_path=day1 / "VISTA.json")
    assert payload["human_verified_label_count"] == 0


# ---------------------------------------------------------------------------
# 4. Records cannot be auto-signed
# ---------------------------------------------------------------------------

def test_no_auto_sign_without_confirmation(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    # Inputs run out at the SIGN prompt -> KeyboardInterrupt; draft survives.
    io = FakeIO(field_inputs(ids))
    with pytest.raises(KeyboardInterrupt):
        run_annotate(
            manifest, "base",
            AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
        )
    assert load_records(record_file(day1, "base")) == []
    draft = json.loads(draft_path(day1, case["case_id"]).read_text(encoding="utf-8"))
    assert "signed" not in draft
    # Standalone sign also requires the typed confirmation.
    io2 = FakeIO(["WRONG"])
    with pytest.raises(KeyboardInterrupt):
        run_sign(manifest, day1, case["case_id"], "ELIAN_PRIMARY", io2)
    assert load_records(record_file(day1, "base")) == []


# ---------------------------------------------------------------------------
# 5. Invalid evidence IDs are rejected
# ---------------------------------------------------------------------------

def test_invalid_evidence_id_rejected(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    fields = field_inputs(ids)
    support_index = BASE_ORDER.index("supporting_evidence_ids")
    inputs = (
        fields[:support_index]
        + ["BOGUS_EVIDENCE_ID_XYZ"]
        + [fields[support_index]]  # retry with a valid id
        + fields[support_index + 1:]
        + [f"SIGN {case['case_id']}"]
    )
    io = FakeIO(inputs)
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    text = "\n".join(io.out)
    assert "unknown evidence IDs: BOGUS_EVIDENCE_ID_XYZ" in text
    assert len(load_records(record_file(day1, "base"))) == 1


# ---------------------------------------------------------------------------
# 6. Enum errors are rejected
# ---------------------------------------------------------------------------

def test_enum_error_rejected(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    fields = field_inputs(ids)
    index = BASE_ORDER.index("question_valid")
    inputs = (
        fields[:index] + ["NOT_A_VALID_LEVEL"] + [fields[index]] + fields[index + 1:]
        + [f"SIGN {case['case_id']}"]
    )
    io = FakeIO(inputs)
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    text = "\n".join(io.out)
    assert "invalid: must be one of" in text
    record = load_records(record_file(day1, "base"))[0]
    assert record["question_valid"] == "VALID"


# ---------------------------------------------------------------------------
# 7. Signed records cannot be overwritten
# ---------------------------------------------------------------------------

def test_signed_records_never_overwritten(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    case_id = case["case_id"]
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    io = FakeIO(field_inputs(ids) + [f"SIGN {case_id}"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    assert len(load_records(record_file(day1, "base"))) == 1
    # Re-annotation without --resume refuses.
    with pytest.raises(CliError, match="already signed"):
        run_annotate(
            manifest, "base",
            AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case_id),
            FakeIO([]), day1_dir=day1,
        )
    # Standalone sign of a signed case refuses.
    with pytest.raises(CliError, match="already signed"):
        run_sign(manifest, day1, case_id, "ELIAN_PRIMARY", FakeIO([]))
    assert len(load_records(record_file(day1, "base"))) == 1
    # Correction appends a NEW record + audit entry; never overwrites.
    correction_io = FakeIO(
        field_inputs(ids, values={"final_answer_or_null": "101"})
        + [f"CORRECT {case_id}"]
    )
    run_correct(
        manifest, day1, "base", case_id, "ELIAN_PRIMARY",
        "fixture correction", correction_io,
    )
    records = load_records(record_file(day1, "base"))
    assert len(records) == 2
    assert records[0]["final_answer_or_null"] == 100.0
    assert records[1]["final_answer_or_null"] == 101.0
    audit = json.loads(
        (day1 / "CORRECTIONS_AUDIT.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert audit["old_record_hash"] == sha256_hex(canonical_json(records[0]))
    assert audit["new_record_hash"] == sha256_hex(canonical_json(records[1]))
    assert audit["reason"] == "fixture correction"


# ---------------------------------------------------------------------------
# 8. Resume skips signed cases
# ---------------------------------------------------------------------------

def test_resume_skips_signed(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    first_id, second_id = case_ids(manifest)[:2]
    first = case_of(manifest, first_id)
    second = case_of(manifest, second_id)
    ids1 = [e["evidence_id"] for e in first["evidence_items"]]
    io = FakeIO(field_inputs(ids1) + [f"SIGN {first_id}"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=first_id),
        io, day1_dir=day1,
    )
    ids2 = [e["evidence_id"] for e in second["evidence_items"]]
    io2 = FakeIO(field_inputs(ids2) + [f"SIGN {second_id}"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", resume=True, limit=1),
        io2, day1_dir=day1,
    )
    text = "\n".join(io2.out)
    assert f"skip {first_id} (already signed)" in text
    assert second_id in text
    assert len(load_records(record_file(day1, "base"))) == 2


# ---------------------------------------------------------------------------
# 9. Blind pass refuses before the waiting period / with incomplete base
# ---------------------------------------------------------------------------

def test_blind_refuses_before_waiting_period(
    env: tuple[Path, dict[str, Any]],
) -> None:
    day1, manifest = env
    seed_base_signed(day1, manifest, hours_ago=1.0)
    with pytest.raises(CliError, match="not before"):
        run_annotate(
            manifest, "blind",
            AnnotateOptions(reviewer_id="ELIAN_PRIMARY"),
            FakeIO([]), day1_dir=day1,
        )
    # Status surfaces the earliest allowed time.
    status_io = FakeIO([])
    run_status(manifest, status_io, day1_dir=day1)
    assert "earliest blind repeat" in "\n".join(status_io.out)


def test_blind_requires_all_22_base_signed(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    # Only 3 base records signed.
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        json.dumps({"case_id": case_id, "signed_by": "fixture", "timestamp": ts})
        for case_id in case_ids(manifest)[:3]
    ]
    record_file(day1, "base").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CliError, match="3/"):
        run_annotate(
            manifest, "blind",
            AnnotateOptions(reviewer_id="ELIAN_PRIMARY"),
            FakeIO([]), day1_dir=day1,
        )


# ---------------------------------------------------------------------------
# 10. Blind pass cannot access pass-1 fields
# ---------------------------------------------------------------------------

def test_blind_hides_pass1_fields_and_case_identity(
    env: tuple[Path, dict[str, Any]],
) -> None:
    day1, manifest = env
    seed_base_signed(day1, manifest, hours_ago=5.0, notes="TOPSECRETPASS1")
    selection = manifest["sealed"]["blind_repeat_5_selection"]
    row = selection[0]
    case = case_of(manifest, row["case_id"])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    io = FakeIO(field_inputs(ids) + [f"SIGN {row['temp_id']}"])
    run_annotate(
        manifest, "blind",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", limit=1),
        io, day1_dir=day1,
    )
    text = "\n".join(io.out)
    assert "TOPSECRETPASS1" not in text  # pass-1 notes never surface
    assert row["case_id"] not in text  # underlying case identity hidden
    assert row["temp_id"] in text
    assert load_records(record_file(day1, "blind"))[0]["pass"] == 2


# ---------------------------------------------------------------------------
# 11. Queue manifest and hashes remain unchanged
# ---------------------------------------------------------------------------

def test_manifest_and_hashes_unchanged(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    manifest_path = day1 / "QUEUE_MANIFEST.json"
    frozen_path = day1 / "FROZEN.sha256"
    before_manifest = manifest_path.read_bytes()
    before_frozen = frozen_path.read_text(encoding="utf-8")
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    # Annotate + sign + correct.
    io = FakeIO(field_inputs(ids) + [f"SIGN {case['case_id']}"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    correction_io = FakeIO(
        field_inputs(ids, values={"final_answer_or_null": "99"})
        + [f"CORRECT {case['case_id']}"]
    )
    run_correct(
        manifest, day1, "base", case["case_id"], "ELIAN_PRIMARY",
        "fixture correction", correction_io,
    )
    assert manifest_path.read_bytes() == before_manifest
    assert frozen_path.read_text(encoding="utf-8") == before_frozen
    assert verify_frozen(day1_dir=day1)["verified"] is True


# ---------------------------------------------------------------------------
# 12. Ctrl+C-safe draft persistence
# ---------------------------------------------------------------------------

def test_ctrl_c_preserves_draft(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    case_id = case["case_id"]
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    # No SIGN input -> KeyboardInterrupt at the confirmation prompt.
    io = FakeIO(field_inputs(ids))
    with pytest.raises(KeyboardInterrupt):
        run_annotate(
            manifest, "base",
            AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
        )
    draft = draft_path(day1, case_id)
    assert draft.exists()
    stored = json.loads(draft.read_text(encoding="utf-8"))
    assert stored["final_answer_or_null"] == 100.0
    assert stored["reviewer_notes"] == "fixture notes"
    assert "signed" not in stored  # never auto-signed
    assert load_records(record_file(day1, "base")) == []
    # The draft is reviewable exactly as stored.
    review_io = FakeIO([])
    run_review_draft(day1, case_id, review_io)
    assert review_io.out == [draft.read_text(encoding="utf-8").rstrip("\n")]
    # Signing completes from the preserved draft.
    sign_io = FakeIO([f"SIGN {case_id}"])
    run_sign(manifest, day1, case_id, "ELIAN_PRIMARY", sign_io)
    assert len(load_records(record_file(day1, "base"))) == 1
    assert not draft.exists()


# ---------------------------------------------------------------------------
# Interface pilot: respects the frozen A/B/C display conditions
# ---------------------------------------------------------------------------

def test_interface_respects_display_conditions(
    env: tuple[Path, dict[str, Any]],
) -> None:
    day1, manifest = env
    cases = manifest["sealed"]["interface_9_cases"]
    for condition, must_have, must_not_have in (
        ("answer_only", "Candidate answer", "Top-k pages"),
        ("answer_topk_pages", "Top-k pages", "VISTA package"),
        ("answer_vista_package", "VISTA package", None),
    ):
        interface_case = next(c for c in cases if c["display_condition"] == condition)
        io = FakeIO(
            interface_inputs() + [f"SIGN {interface_case['case_id']}"]
        )
        run_annotate(
            manifest, "interface",
            AnnotateOptions(reviewer_id="ELIAN_PRIMARY",
                            case_id=interface_case["case_id"]),
            io, day1_dir=day1,
        )
        text = "\n".join(io.out)
        assert f"Display condition: {condition}" in text
        assert must_have in text
        if must_not_have:
            assert must_not_have not in text
    records = load_records(record_file(day1, "interface"))
    assert len(records) == 3
    assert all(r["record_type"] == "INTERFACE_PILOT" for r in records)
    assert all(r["signed"] is True for r in records)


# ---------------------------------------------------------------------------
# Status: counts and violations
# ---------------------------------------------------------------------------

def test_status_counts_and_violations(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    case = case_of(manifest, case_ids(manifest)[0])
    ids = [e["evidence_id"] for e in case["evidence_items"]]
    io = FakeIO(field_inputs(ids) + [f"SIGN {case['case_id']}"])
    run_annotate(
        manifest, "base",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=case["case_id"]), io, day1_dir=day1,
    )
    status_io = FakeIO([])
    run_status(manifest, status_io, day1_dir=day1)
    text = "\n".join(status_io.out)
    assert "base signed:            1 / 22" in text
    assert "violations:             0" in text
    # A hand-tampered record (bad enum) is flagged.
    bad = {
        "record_type": "BASE_22", "case_id": case["case_id"],
        "signed": True, "signed_by": "ELIAN_PRIMARY",
        "timestamp": "2026-08-06T00:00:00+00:00",
        "sufficiency": "NOT_A_VALUE",
    }
    with record_file(day1, "base").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(bad, sort_keys=True) + "\n")
    status_io2 = FakeIO([])
    run_status(manifest, status_io2, day1_dir=day1)
    text2 = "\n".join(status_io2.out)
    assert "violations:" in text2
    assert "sufficiency: invalid value" in text2


# ---------------------------------------------------------------------------
# Paired queue: neutral tokens only
# ---------------------------------------------------------------------------

def test_paired_uses_neutral_tokens(env: tuple[Path, dict[str, Any]]) -> None:
    day1, manifest = env
    row = manifest["reviewer_view"]["paired_12"][0]
    token = row["review_token"]
    ids = [e["evidence_id"] for e in row["evidence"]]
    io = FakeIO(field_inputs(ids) + [f"SIGN {token}"])
    run_annotate(
        manifest, "paired",
        AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id=token),
        io, day1_dir=day1,
    )
    text = "\n".join(io.out)
    assert "Condition identity: hidden during review" in text
    assert "instance_id" not in text  # condition-embedding id never shown
    record = load_records(record_file(day1, "paired"))[0]
    assert record["review_token"] == token
    assert record["condition_identity"] == "HIDDEN_DURING_REVIEW"
    # Unknown tokens are rejected.
    with pytest.raises(CliError, match="not in the paired queue"):
        run_annotate(
            manifest, "paired",
            AnnotateOptions(reviewer_id="ELIAN_PRIMARY", case_id="pr-99"),
            FakeIO([]), day1_dir=day1,
        )
