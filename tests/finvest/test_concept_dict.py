"""Tests for the public concept dictionary + question->concept induction.

Covers N-6: real benchmark questions spell concepts in camelCase (e.g.
'AccruedLiabilitiesCurrent'), which never matched the dictionary's
space-separated keys ('accrued liabilities'), so induction degraded to a
broader term (e.g. 'Liabilities') and S2/S3 + R4 selected nothing useful.
"""

from __future__ import annotations

from finvest.retrieval.retrievers import _concepts_for


def test_camelcase_question_matches_dictionary() -> None:
    """A camelCase-spelled concept must induce the exact dictionary concept.

    The question 'What is ... AccruedLiabilitiesCurrent ...' must yield
    AccruedLiabilitiesCurrent, not just the broader Liabilities.
    """
    pred = _concepts_for(
        "What is the latest restated value of AccruedLiabilitiesCurrent "
        "for AAPL for the period ending 2008-09-27?"
    )
    assert "AccruedLiabilitiesCurrent" in pred, (
        "camelCase concept spelling must match the dictionary (N-6)"
    )


def test_plain_spaced_question_matches() -> None:
    pred = _concepts_for("What is AAPL operating cash flow for 2024?")
    assert "NetCashProvidedByUsedInOperatingActivities" in pred


def test_cashflow_question_predicts_both_concepts() -> None:
    """The cashflow-proxy cases need both OCF and capex concepts."""
    pred = _concepts_for(
        "What is AAPL operating cash flow minus capital expenditure "
        "for the fiscal period 2024?"
    )
    assert "NetCashProvidedByUsedInOperatingActivities" in pred
    assert "PaymentsToAcquirePropertyPlantAndEquipment" in pred


def test_unknown_concept_returns_empty() -> None:
    assert _concepts_for("What is the price-to-earnings ratio of X?") == set()
