"""Practice-mode tests (Phase 10/11) — practice never enters formal results.

Phase 11: the practice record stores the researcher's 3 natural-question
answers FIRST (q1/q2/q3), and the reference answer is only attached at
record time (reveal-after-submit), so the stored record always captures the
independent judgement.
"""

from __future__ import annotations

import json
from pathlib import Path

from finvest.human_study.web.services.practice_mode import (
    PRACTICE_REQUIRED_COUNT,
    practice_summary,
    record_practice,
)


def _record(path: Path, case_id: str, *, q1: str = "ANSWERABLE",
            reference: str = "ans") -> None:
    record_practice(
        practice_path=path, case_id=case_id,
        q1_answerable=q1,
        q2_answer_and_calc="118e9 - 11e9 = 107e9",
        q3_conflicts="",
        your_calculation="107,000,000,000",
        reference_answer=reference,
        source_explanation="why",
        disagreement_reason=None,
        reviewer_id="ELIAN_PRIMARY",
    )


def test_practice_requires_five(tmp_path: Path) -> None:
    path = tmp_path / "practice.jsonl"
    s0 = practice_summary(path)
    assert s0.completed == 0
    assert s0.ready is False
    # 4 practice records -> not ready.
    for i in range(4):
        _record(path, f"c{i}")
    s4 = practice_summary(path)
    assert s4.completed == 4
    assert s4.ready is False
    # 5th -> ready.
    _record(path, "c4")
    s5 = practice_summary(path)
    assert s5.completed == 5
    assert s5.ready is True


def test_practice_record_is_not_a_label(tmp_path: Path) -> None:
    path = tmp_path / "practice.jsonl"
    _record(path, "c1")
    raw = path.read_text(encoding="utf-8").strip()
    entry = json.loads(raw)
    # Practice is explicitly not a signed human label.
    assert "signed_by" not in entry or entry.get("signed") is not True
    assert entry["reviewer_id"] == "ELIAN_PRIMARY"
    # The researcher's own answers are stored (not a machine label).
    assert entry["q1_answerable"] == "ANSWERABLE"
    assert "107e9" in entry["q2_answer_and_calc"]
    assert entry["reference_answer"] == "ans"  # attached at record time only
