from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_e7_runner_writes_parseable_output() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_e7_commercial.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout)
    assert payload["all_ok"] is True
    assert set(payload["companies"]) == {"EQIX", "JNJ", "UPS", "AAPL", "MSFT", "KO"}
    for ticker, info in payload["companies"].items():
        assert "domain" in info
        for year, analysis in info["years"].items():
            assert "metrics" in analysis
            assert "evidence_sufficiency" in analysis
            assert "evidence_sources" in analysis
    out_path = ROOT / "research/results/e7_commercial_summary.json"
    assert out_path.exists()
    assert out_path.stat().st_size > 0
