from __future__ import annotations

from finvest.benchmark.leakage_audit import (
    audit_duplicate_pairs,
    audit_source_for_gold,
    audit_split,
    hash_content,
    minhash_sketch,
)
from finvest.benchmark.splitters import split_by_issuer, split_chronological
from datetime import date, datetime

from finvest.benchmark.schemas import FinVESTCase, EvidenceItem


def _case(case_id: str, issuer: str, cutoff: str) -> FinVESTCase:
    return FinVESTCase(
        case_id=case_id, base_question_id=f"bq-{case_id}", issuer_id=issuer,
        jurisdiction="US", question=f"question {case_id}",
        source_cutoff=datetime.fromisoformat(cutoff),
        target_period_start=date(2024, 1, 1), target_period_end=date(2024, 12, 31),
        target_fiscal_year="FY2024", answer_type="extractive",
        gold_answer={"v": 1}, decision_label="ANSWER", sufficiency_label="SUPPORTED",
        evidence_items=(EvidenceItem(evidence_id=f"ev-{case_id}", document_id="d", document_version="10-K", filing_date=date(2024, 3, 1)),),
    )


def test_split_by_issuer() -> None:
    cases = [
        _case("c1", "AAPL", "2024-03-01"),
        _case("c2", "AAPL", "2024-03-01"),
        _case("c3", "MSFT", "2024-03-01"),
    ]
    split = split_by_issuer(cases, test_issuers={"MSFT"})
    assert set(split.train) == {"c1", "c2"}
    assert set(split.test) == {"c3"}
    assert split.is_disjoint()


def test_split_chronological() -> None:
    cases = [
        _case("c1", "AAPL", "2024-03-01"),
        _case("c2", "AAPL", "2025-03-01"),
    ]
    split = split_chronological(cases, cutoff=date(2024, 12, 31))
    assert set(split.train) == {"c1"}
    assert set(split.test) == {"c2"}


def test_audit_split_detects_issuer_leak() -> None:
    violations = audit_split(
        issuer_of={"c1": "AAPL", "c2": "AAPL"},
        family_of={"c1": "f1", "c2": "f2"},
        train=["c1"], test=["c2"],
    )
    assert any("issuer" in v for v in violations)


def test_audit_source_for_gold() -> None:
    leaky = "coverage = len(retrieved & relevant_by_question[qid]) / len(relevant)"
    clean = "margin = top1.score - top2.score"
    assert audit_source_for_gold(leaky)
    assert not audit_source_for_gold(clean)


def test_duplicate_pairs_detected() -> None:
    texts = {
        "a": "Apple revenue was 391 billion in fiscal 2024 per the annual report.",
        "b": "Apple revenue was 391 billion in fiscal 2024 per the annual report.",
        "c": "Microsoft net income for fiscal 2025 was reported as 88 billion.",
    }
    pairs = audit_duplicate_pairs(texts, threshold=0.6)
    pair_ids = {(a, b) for a, b, _ in pairs}
    assert ("a", "b") in pair_ids
    assert all("c" not in p for p in pair_ids)


def test_hash_and_sketch() -> None:
    assert hash_content("abc") == hash_content("abc")
    assert hash_content("abc") != hash_content("abd")
    s1 = minhash_sketch("the quick brown fox jumps over the lazy dog")
    s2 = minhash_sketch("the quick brown fox jumps over the lazy dog")
    assert s1 == s2
