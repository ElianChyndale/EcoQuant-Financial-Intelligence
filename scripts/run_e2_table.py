"""One-command E2 table + numerical reasoning evaluation over GRI-QA quant.

Usage: python scripts/run_e2_table.py
Writes research/results/e2_table_summary.json with per-method metrics. Exits 0
iff all methods scored.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/results/e2_table_summary.json"


def _numeric_exact(prediction: float | None, gold: float) -> bool:
    if prediction is None:
        return False
    return math.isclose(prediction, gold, rel_tol=0.0, abs_tol=1e-6)


def _tolerance_1pct(prediction: float | None, gold: float) -> bool:
    if prediction is None or gold == 0:
        return False
    return abs(prediction - gold) / abs(gold) <= 0.01


def _evaluate(predictions: dict[str, float | None], bundle) -> dict[str, object]:
    total = len(bundle.questions)
    answered = sum(1 for v in predictions.values() if v is not None)
    gold_by_id = {q.question_id: q.value for q in bundle.questions}
    exact = sum(
        _numeric_exact(predictions[qid], gold) for qid, gold in gold_by_id.items()
    )
    tol = sum(
        _tolerance_1pct(predictions[qid], gold) for qid, gold in gold_by_id.items()
    )
    return {
        "question_count": total,
        "answered": answered,
        "unsupported": total - answered,
        "unsupported_rate": (total - answered) / total,
        "numeric_exact_match": exact / total,
        "tolerance_1pct_accuracy": tol / total,
        "exact_among_answered": exact / answered if answered else 0.0,
    }


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from ecoquant.research.table_eval.baselines import run_b3_table_only, run_b7_long_context, run_proposed
    from ecoquant.research.table_eval.griqa import load_griqa_quant

    bundle = load_griqa_quant(ROOT / "research/cache/griqa")

    methods = {
        "b3_table_only": run_b3_table_only(bundle),
        "b7_long_context": run_b7_long_context(bundle),
        "proposed": run_proposed(bundle),
    }
    scored = {name: _evaluate(preds, bundle) for name, preds in methods.items()}

    payload = {
        "experiment": "e2-table-numerical-reasoning",
        "note": (
            "GRI-QA quant (266 real environmental-table questions, 6 calc types, "
            "27 tables). B1 (LLM direct) blocked: no LLM API. B7 uses gold table "
            "(no retrieval); B3 and proposed use BM25 retrieval."
        ),
        "dataset": {
            "question_count": len(bundle.questions),
            "table_count": len(bundle.tables),
            "license": bundle.manifest["license"],
        },
        "methods": scored,
        "all_ok": all("numeric_exact_match" in m for m in scored.values()),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
