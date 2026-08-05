from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e8_runner_writes_parseable_output() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e8_integration.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout)
    assert payload["all_ok"] is True
    comparison = payload["comparison"]
    assert "legacy" in comparison and "proposed" in comparison
    assert "unsupported_risk_flag_rate" in comparison["legacy"]
    assert "citation_validity" in comparison["proposed"]
    assert "decision_distribution" in comparison
    assert comparison["case_count"] == 6
    out_path = ROOT / "research/results/e8_integration_summary.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
