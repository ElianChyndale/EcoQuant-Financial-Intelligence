from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e5_runner_writes_parseable_output() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e5_calibration.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=900,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout)
    assert payload["all_ok"] is True
    metrics = payload["metrics"]
    assert "fold_count" in metrics
    assert "ece" in metrics and "brier" in metrics and "auc" in metrics
    assert "coverage_at_90pct_precision" in metrics
    assert "coverage_at_95pct_precision" in metrics
    assert "risk_coverage_frontier" in metrics
    assert payload["dataset"]["company_count"] >= 4
    out_path = ROOT / "research/results/e5_calibration_summary.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
