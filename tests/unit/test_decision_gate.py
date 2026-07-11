"""Decision precedence and gating tests for Task 6."""

from __future__ import annotations

import pytest

from ecoquant.uncertainty.decision import DecisionCode, decide


class TestDecisionPrecedence:
    """Invalid extraction or missing evidence overrides high confidence."""

    def test_invalid_extraction_is_insufficient_evidence(self) -> None:
        decision = decide(
            calibrated_probability=0.99,
            conforms=True,
            evidence_sufficiency=0.0,
            extraction_valid=False,
        )
        assert decision.code is DecisionCode.INSUFFICIENT_EVIDENCE

    def test_low_evidence_sufficiency_is_insufficient(self) -> None:
        decision = decide(
            calibrated_probability=0.95,
            conforms=True,
            evidence_sufficiency=0.1,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.INSUFFICIENT_EVIDENCE

    def test_high_confidence_but_no_conformal_is_review(self) -> None:
        decision = decide(
            calibrated_probability=0.95,
            conforms=False,
            evidence_sufficiency=0.8,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED

    def test_uncertain_supported_case_requires_review(self) -> None:
        decision = decide(0.62, False, 0.75, True)
        assert decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED

    def test_auto_report_requires_all_gates(self) -> None:
        decision = decide(
            calibrated_probability=0.92,
            conforms=True,
            evidence_sufficiency=0.85,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.AUTO_REPORT

    def test_auto_report_fails_without_conformal(self) -> None:
        decision = decide(
            calibrated_probability=0.92,
            conforms=False,
            evidence_sufficiency=0.85,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED

    def test_auto_report_fails_with_low_probability(self) -> None:
        decision = decide(
            calibrated_probability=0.50,
            conforms=True,
            evidence_sufficiency=0.85,
            extraction_valid=True,
        )
        assert decision.code is DecisionCode.HUMAN_REVIEW_REQUIRED

    def test_decision_code_ordering(self) -> None:
        assert DecisionCode.INSUFFICIENT_EVIDENCE < DecisionCode.HUMAN_REVIEW_REQUIRED
        assert DecisionCode.HUMAN_REVIEW_REQUIRED < DecisionCode.AUTO_REPORT

    def test_decision_exposes_code(self) -> None:
        decision = decide(0.5, False, 0.5, True)
        assert hasattr(decision, "code")
        assert isinstance(decision.code, DecisionCode)
