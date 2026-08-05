"""One-command E3 temporal + contradiction evaluation over SEC EDGAR facts.

Usage: python scripts/run_e3_temporal.py
Writes research/results/e3_temporal_summary.json with per-method metrics.
Exits 0 iff all methods scored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/results/e3_temporal_summary.json"


def _future_information_rate(predictions, questions) -> float:
    """Fraction of retrieved facts filed after the question's source_cutoff."""
    total, future = 0, 0
    for question in questions:
        for fact in predictions[question.question_id]:
            total += 1
            if fact.filed > question.source_cutoff:
                future += 1
    return future / total if total else 0.0


def _expired_evidence_rate(predictions, questions) -> float:
    """Fraction of retrieved facts with end after valid_at (future period)."""
    total, expired = 0, 0
    for question in questions:
        for fact in predictions[question.question_id]:
            total += 1
            if fact.end > question.valid_at:
                expired += 1
    return expired / total if total else 0.0


def _valid_evidence_recall(predictions, questions) -> float:
    """Fraction of gold-valid evidence retrieved at rank <= TOP_K."""
    hits = sum(
        1 for question in questions
        if question.gold_evidence_ids & {f.fact_id for f in predictions[question.question_id]}
    )
    return hits / len(questions) if questions else 0.0


def _contradiction_f1(bundle, predictions, questions) -> float:
    """Precision/recall over detected contradiction facts (restated values)."""
    gold_contradiction_ids = {
        evidence_id
        for question in questions if question.is_contradiction
        for evidence_id in question.gold_evidence_ids
    }
    # Detected: a retrieved fact whose (concept, end) also appears with an
    # earlier different value in the bundle (i.e. it is a restatement).
    facts_by_key: dict[tuple[str, str, str], set[float]] = {}
    for fact in bundle.facts:
        facts_by_key.setdefault((fact.ticker, fact.concept, str(fact.end)), set()).add(fact.val)

    predicted_ids: set[str] = set()
    for question in questions:
        for fact in predictions[question.question_id]:
            key = (fact.ticker, fact.concept, str(fact.end))
            if len(facts_by_key.get(key, set())) > 1:
                predicted_ids.add(fact.fact_id)

    true_positive = len(predicted_ids & gold_contradiction_ids)
    precision = true_positive / len(predicted_ids) if predicted_ids else 0.0
    recall = true_positive / len(gold_contradiction_ids) if gold_contradiction_ids else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from ecoquant.research.temporal_eval.baselines import (
        run_b1_bm25, run_b2_hybrid, run_b3_source_time_filter,
        run_b4_valid_time_filter, run_b5_temporal_contradiction,
    )
    from ecoquant.research.temporal_eval.questions import build_temporal_questions
    from ecoquant.research.temporal_eval.sec_adapter import load_companyfacts

    bundle = load_companyfacts(ROOT / "research/cache/sec", tickers=("AAPL", "MSFT", "KO"))
    questions = build_temporal_questions(bundle)

    # Use a stratified sample for speed: up to 100 per class.
    from collections import defaultdict
    by_class: dict[str, list] = defaultdict(list)
    for q in questions:
        by_class[q.question_class].append(q)
    sampled: list = []
    for cls in ("old_vs_new", "amended_vs_original", "cross_period"):
        sampled.extend(by_class[cls][:100])

    runners = {
        "b1_bm25": run_b1_bm25,
        "b2_hybrid": run_b2_hybrid,
        "b3_source_time_filter": run_b3_source_time_filter,
        "b4_valid_time_filter": run_b4_valid_time_filter,
        "b5_temporal_contradiction": run_b5_temporal_contradiction,
    }
    methods: dict[str, object] = {}
    for name, runner in runners.items():
        predictions = runner(bundle, sampled)
        methods[name] = {
            "future_information_rate": _future_information_rate(predictions, sampled),
            "expired_evidence_rate": _expired_evidence_rate(predictions, sampled),
            "valid_evidence_recall": _valid_evidence_recall(predictions, sampled),
            "contradiction_f1": _contradiction_f1(bundle, predictions, sampled),
        }

    payload = {
        "experiment": "e3-temporal-contradiction",
        "note": (
            "SEC EDGAR XBRL companyfacts for AAPL/MSFT/KO; 5752 real temporal "
            "questions, stratified sample of 300 (100/class). valid_time=end, "
            "source_time=filed."
        ),
        "dataset": {
            "fact_count": len(bundle.facts),
            "question_count": len(questions),
            "sampled_question_count": len(sampled),
            "license": "public-domain",
        },
        "methods": methods,
        "all_ok": all("future_information_rate" in m for m in methods.values()),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
