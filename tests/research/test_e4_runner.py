from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e4_runner_writes_parseable_output() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e4_verification.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout)
    assert payload["all_ok"] is True
    assert "supported_answer_accuracy" in payload["metrics"]
    assert "false_pass_rate" in payload["metrics"]
    assert "unsupported_rejected_rate" in payload["metrics"]
    assert payload["dataset"]["supported_cases"] > 0
    assert payload["dataset"]["unsupported_cases"] > 0
    out_path = ROOT / "research/results/e4_verification_summary.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
