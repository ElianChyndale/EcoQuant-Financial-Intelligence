from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e2_runner_writes_parseable_output() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e2_table.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout)
    assert payload["all_ok"] is True
    assert set(payload["methods"]) == {"b3_table_only", "b7_long_context", "proposed"}
    assert payload["dataset"]["question_count"] == 266
    for method in payload["methods"].values():
        assert method["question_count"] == 266
        assert "numeric_exact_match" in method
        assert "unsupported_rate" in method
    out_path = ROOT / "research/results/e2_table_summary.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
