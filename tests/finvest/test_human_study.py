from __future__ import annotations

import pytest

from finvest.human_study.protocol import (
    Condition,
    ReviewCase,
    ReviewLabel,
    assign_cases,
    latin_square,
    mixed_effects_summary,
    verify_labels_are_human,
)


def test_latin_square_counterbalancing() -> None:
    order = [Condition.A, Condition.B, Condition.C]
    r0 = latin_square(order, 0)
    r1 = latin_square(order, 1)
    assert r0 == [Condition.A, Condition.B, Condition.C]
    assert r1 == [Condition.B, Condition.C, Condition.A]
    # Each reviewer sees all conditions in a different order.
    assert set(r0) == set(r1) == set(order)


def test_assign_cases_stratified() -> None:
    cases = [
        ReviewCase(f"c{i}", f"q{i}", Condition.A, "ans")
        for i in range(30)
    ] + [
        ReviewCase(f"c{i}", f"q{i}", Condition.B, "ans")
        for i in range(30, 60)
    ] + [
        ReviewCase(f"c{i}", f"q{i}", Condition.C, "ans")
        for i in range(60, 90)
    ]
    assigned = assign_cases(cases, "r1", 1, cases_per_reviewer=9)
    assert len(assigned) == 9
    conditions = {c.condition for c in assigned}
    assert conditions == {Condition.A, Condition.B, Condition.C}


def test_summary_shape() -> None:
    labels = [
        ReviewLabel("r1", "c1", "rev1", "A", True, True, True, False, False, 60.0, 4, signed=True),
        ReviewLabel("r2", "c1", "rev2", "A", False, False, False, True, True, 120.0, 2, signed=True),
        ReviewLabel("r3", "c2", "rev1", "C", True, True, True, False, False, 45.0, 5, signed=True),
    ]
    summary = mixed_effects_summary(labels)
    assert summary["n_reviews"] == 3
    assert "by_condition" in summary
    for cond_data in summary["by_condition"].values():
        assert "unsafe_acceptance_rate" in cond_data
        assert "median_review_time_seconds" in cond_data


def test_human_signature_required() -> None:
    unsigned = ReviewLabel("r1", "c1", "rev1", "A", True, True, True, False, False, 60.0, 4, signed=False)
    signed = ReviewLabel("r2", "c1", "rev2", "A", True, True, True, False, False, 60.0, 4, signed=True)
    violations = verify_labels_are_human([unsigned, signed])
    assert violations == ["r1"]
