from __future__ import annotations

from pathlib import Path

import pytest

from ecoquant.research.integration_eval.evidence_pipeline import (
    EvidencePipelineOutput,
    run_evidence_pipeline,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def config():
    return {"cache_dir": ROOT / "research/cache", "seed": 20260806}


def test_pipeline_produces_evidence_bundle(config) -> None:
    out = run_evidence_pipeline(
        "What is AAPL total revenue for fiscal 2024?", "AAPL", 2024, config=config,
    )
    assert isinstance(out, EvidencePipelineOutput)
    assert out.evidence_bundle  # non-empty, source-linked
    assert out.verification_state
    assert 0.0 <= out.calibrated_confidence <= 1.0
    assert out.decision in ("AUTO_REPORT", "HUMAN_REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE")
    assert out.review_status in ("auto", "review")


def test_pipeline_is_deterministic(config) -> None:
    a = run_evidence_pipeline("What is AAPL revenue 2024?", "AAPL", 2024, config=config)
    b = run_evidence_pipeline("What is AAPL revenue 2024?", "AAPL", 2024, config=config)
    assert a.decision == b.decision
    assert a.calibrated_confidence == b.calibrated_confidence
    assert a.evidence_bundle == b.evidence_bundle


def test_pipeline_never_decides_spread(config) -> None:
    """Boundary: the AI never sets a credit spread — only attestation + status."""
    out = run_evidence_pipeline("What is AAPL revenue 2024?", "AAPL", 2024, config=config)
    assert "spread_bps" not in out.__dict__


def test_attestation_only_when_auto_report(config) -> None:
    """AUTO_REPORT produces a signed attestation; other states produce none."""
    out = run_evidence_pipeline("What is AAPL revenue 2024?", "AAPL", 2024, config=config)
    if out.decision == "AUTO_REPORT":
        assert out.attestation is not None
        assert out.attestation["decision_code"] == 2
    else:
        assert out.attestation is None
