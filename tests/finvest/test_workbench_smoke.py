"""Workbench smoke test — isolated, never touches real signed JSONL."""

from __future__ import annotations

import tempfile
from pathlib import Path

from finvest.human_study.web.smoke_test import run_smoke_test


def test_smoke_test_passes_isolated() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="finvest-smoke-test-"))
    result = run_smoke_test(tmp)
    assert result["all_pass"] is True
    assert len(result["queues"]) == 4  # base_22, paired_12, interface_9, blind_repeat_5
    assert result["evidence_count"] > 0
    assert result["draft_autosaved"] is True
    assert result["signing_requires_confirmation"] is True
    assert result["no_signed_jsonl"] is True
    assert result["no_outbound_imports"] is True
