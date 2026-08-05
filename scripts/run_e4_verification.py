"""One-command E4 citation + evidence verification evaluation.

Usage: python scripts/run_e4_verification.py
Builds the verification benchmark (supported + injected unsupported cases),
runs the multi-layer verifier, reports supported-answer accuracy and the
critical false-pass rate. Writes research/results/e4_verification_summary.json.
Exits 0 iff evaluation completed.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/results/e4_verification_summary.json"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from ecoquant.research.verification_eval.benchmark import build_benchmark_cases
    from ecoquant.research.verification_eval.verifier import verify_claim

    cases = build_benchmark_cases(ROOT)
    results: list[dict[str, object]] = []
    for case in cases:
        verification = verify_claim(case.claim_input)
        results.append({
            "case_id": case.case_id,
            "gold_state": case.gold_state,
            "verified_state": verification.state,
            "layer_results": verification.layer_results,
            "reason": verification.reason,
        })

    supported = [r for r in results if r["gold_state"] == "SUPPORTED"]
    unsupported = [r for r in results if r["gold_state"] == "INSUFFICIENT_EVIDENCE"]

    supported_accuracy = sum(
        1 for r in supported if r["verified_state"] == "SUPPORTED"
    ) / len(supported) if supported else 0.0
    # FALSE-PASS RATE: unsupported answers wrongly accepted as SUPPORTED.
    false_pass = sum(
        1 for r in unsupported if r["verified_state"] == "SUPPORTED"
    )
    false_pass_rate = false_pass / len(unsupported) if unsupported else 0.0
    # Correctly-rejected rate (unsupported → not SUPPORTED).
    rejected_rate = 1.0 - false_pass_rate

    state_distribution = Counter(r["verified_state"] for r in results)

    payload = {
        "experiment": "e4-evidence-verification",
        "note": (
            "Multi-layer verifier (citation, number grounding, year/unit/scale, "
            "calculation, conflict) over FinanceBench + GRI-QA cases with injected "
            "unsupported examples. False-pass rate is the critical metric."
        ),
        "dataset": {
            "total_cases": len(results),
            "supported_cases": len(supported),
            "unsupported_cases": len(unsupported),
        },
        "metrics": {
            "supported_answer_accuracy": supported_accuracy,
            "false_pass_rate": false_pass_rate,
            "unsupported_rejected_rate": rejected_rate,
            "false_pass_count": false_pass,
        },
        "state_distribution": dict(state_distribution),
        "results": results,
        "all_ok": bool(results),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
