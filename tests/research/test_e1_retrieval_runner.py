from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e1_runner_writes_parseable_output() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e1_retrieval.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=900,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout)
    assert payload["all_ok"] is True
    # Both datasets scored all six methods.
    assert set(payload["datasets"]["financebench"]["methods"]) == {
        "bm25", "tfidf", "lsa", "dense", "hybrid_rrf", "long_context",
    }
    assert set(payload["datasets"]["ecoquant_corpus"]["methods"]) == {
        "bm25", "tfidf", "lsa", "dense", "hybrid_rrf", "long_context",
    }
    # FinanceBench has 150 questions; EcoQuant has 64.
    assert payload["datasets"]["financebench"]["question_count"] == 150
    assert payload["datasets"]["ecoquant_corpus"]["question_count"] == 64
    # Bootstrap CIs present on the primary metric for every method.
    for dataset in payload["datasets"].values():
        for method in dataset["methods"].values():
            assert "bootstrap_ci_95" in method
    # Artifact is written and non-empty.
    out_path = ROOT / "research/results/e1_retrieval_summary.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
