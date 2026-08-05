"""One-command E8 EcoQuant integration comparison.

Usage: python scripts/run_e8_integration.py
Compares the legacy prompt-only honesty-score system against the proposed
evidence pipeline over a set of commercial questions. Writes
research/results/e8_integration_summary.json. Exits 0 iff comparison completed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/results/e8_integration_summary.json"

# (question, ticker, year) cases across the 6 commercial companies.
CASES = [
    ("What is AAPL total revenue for fiscal 2024?", "AAPL", 2024),
    ("What is MSFT net income for fiscal 2025?", "MSFT", 2025),
    ("What is KO operating income for fiscal 2024?", "KO", 2024),
    ("What is UPS total debt for fiscal 2024?", "UPS", 2024),
    ("What is EQIX revenue for fiscal 2024?", "EQIX", 2024),
    ("What is JNJ net income for fiscal 2024?", "JNJ", 2024),
]


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from ecoquant.research.integration_eval.compare import compare_systems

    comparison = compare_systems(CASES, config={"cache_dir": ROOT / "research/cache", "seed": 20260806})
    payload = {
        "experiment": "e8-ecoquant-integration",
        "note": (
            "Legacy prompt-only honesty score -> (60-score)*2 bps spread vs the "
            "proposed evidence pipeline (retrieval -> verification -> calibrated "
            "confidence -> decision gate -> signed attestation). Boundary enforced: "
            "AI never sets a spread; it produces attestation + evidence + confidence "
            "+ review status."
        ),
        "cases": CASES,
        "comparison": comparison,
        "all_ok": bool(comparison["all_ok"]),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
