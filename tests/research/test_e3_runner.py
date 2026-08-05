from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e3_runner_writes_parseable_output() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e3_temporal.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=600,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout)
    assert payload["all_ok"] is True
    assert set(payload["methods"]) == {
        "b1_bm25", "b2_hybrid", "b3_source_time_filter",
        "b4_valid_time_filter", "b5_temporal_contradiction",
    }
    # Amended-vs-original class has only 34 real restatements, so the sample is
    # 100 + 34 + 100 = 234, not 300.
    assert 0 < payload["dataset"]["sampled_question_count"] <= 300
    for method in payload["methods"].values():
        for key in ("future_information_rate", "expired_evidence_rate",
                    "valid_evidence_recall", "contradiction_f1"):
            assert key in method
    out_path = ROOT / "research/results/e3_temporal_summary.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
