"""Practice-mode tests (Phase 10) — practice never enters formal results."""

from __future__ import annotations

import json
from pathlib import Path

from finvest.human_study.web.services.practice_mode import (
    PRACTICE_REQUIRED_COUNT,
    practice_summary,
    record_practice,
)


def test_practice_requires_five(tmp_path: Path) -> None:
    path = tmp_path / "practice.jsonl"
    s0 = practice_summary(path)
    assert s0.completed == 0
    assert s0.ready is False
    # 4 practice records -> not ready.
    for i in range(4):
        record_practice(
            practice_path=path, case_id=f"c{i}",
            researcher_judgement="SUPPORTED",
            reference_answer="ans", source_explanation="why",
            disagreement_reason=None, reviewer_id="ELIAN_PRIMARY",
        )
    s4 = practice_summary(path)
    assert s4.completed == 4
    assert s4.ready is False
    # 5th -> ready.
    record_practice(
        practice_path=path, case_id="c4",
        researcher_judgement="PARTIAL",
        reference_answer="ans", source_explanation="why",
        disagreement_reason="period mismatch", reviewer_id="ELIAN_PRIMARY",
    )
    s5 = practice_summary(path)
    assert s5.completed == 5
    assert s5.ready is True


def test_practice_record_is_not_a_label(tmp_path: Path) -> None:
    path = tmp_path / "practice.jsonl"
    record_practice(
        practice_path=path, case_id="c1",
        researcher_judgement="SUPPORTED",
        reference_answer="ans", source_explanation="why",
        disagreement_reason=None, reviewer_id="ELIAN_PRIMARY",
    )
    raw = path.read_text(encoding="utf-8").strip()
    entry = json.loads(raw)
    # Practice is explicitly not a signed human label.
    assert "signed_by" not in entry or entry.get("signed") is not True
    assert entry["reviewer_id"] == "ELIAN_PRIMARY"
