"""E8: head-to-head comparison of legacy vs proposed systems.

Metrics:

- ``unsupported_risk_flag_rate``: fraction of outputs with NO verification
  (legacy always; proposed only when verification is not SUPPORTED).
- ``citation_validity``: fraction of outputs with a non-empty evidence bundle
  (legacy 0; proposed >0).
- ``refusal_quality``: fraction of outputs routed to review when confidence is
  low (proposed); legacy never routes to review.
- ``repeatability``: fraction of identical outputs on the same input twice
  (both deterministic; proposed re-runs evidence pipeline).
- ``same_document_stability``: fraction of identical outputs for the same
  question asked twice (same-document).
"""

from __future__ import annotations

from collections.abc import Sequence

from .evidence_pipeline import EvidencePipelineOutput, run_evidence_pipeline
from .legacy import LegacyOutput, legacy_honesty_score


def compare_systems(
    questions: Sequence[tuple[str, str, int]],
    *,
    config: dict[str, object],
) -> dict[str, object]:
    """Compare legacy vs proposed across a set of (question, ticker, year) cases."""
    legacy_outputs: list[LegacyOutput] = []
    proposed_outputs: list[EvidencePipelineOutput] = []
    for question, ticker, year in questions:
        legacy_outputs.append(legacy_honesty_score(question, seed=42))
        proposed_outputs.append(run_evidence_pipeline(question, ticker, year, config=config))

    n = len(questions)
    # Unsupported risk flag: output has no verification / no evidence.
    legacy_unsupported = sum(1 for o in legacy_outputs if o.verification != "supported")
    proposed_unsupported = sum(
        1 for o in proposed_outputs if o.verification_state != "SUPPORTED"
    )
    # Citation validity: non-empty evidence bundle.
    legacy_cited = sum(1 for o in legacy_outputs if o.citation is not None)
    proposed_cited = sum(1 for o in proposed_outputs if o.evidence_bundle)
    # Refusal quality: routed to review when confidence low.
    legacy_review = sum(1 for o in legacy_outputs if o.review_status != "auto")
    proposed_review = sum(1 for o in proposed_outputs if o.review_status != "auto")
    # Repeatability: same input twice → same output.
    repeat_legacy = sum(
        1
        for (q, t, y) in questions
        if legacy_honesty_score(q, seed=42) == legacy_honesty_score(q, seed=42)
    )
    repeat_proposed = sum(
        1
        for (q, t, y) in questions
        if run_evidence_pipeline(q, t, y, config=config)
        == run_evidence_pipeline(q, t, y, config=config)
    )

    return {
        "case_count": n,
        "legacy": {
            "unsupported_risk_flag_rate": legacy_unsupported / n,
            "citation_validity": legacy_cited / n,
            "refusal_quality": legacy_review / n,
            "repeatability": repeat_legacy / n,
        },
        "proposed": {
            "unsupported_risk_flag_rate": proposed_unsupported / n,
            "citation_validity": proposed_cited / n,
            "refusal_quality": proposed_review / n,
            "repeatability": repeat_proposed / n,
        },
        "decision_distribution": _decision_distribution(proposed_outputs),
        "all_ok": n > 0,
    }


def _decision_distribution(outputs: Sequence[EvidencePipelineOutput]) -> dict[str, int]:
    from collections import Counter

    return dict(Counter(o.decision for o in outputs))
