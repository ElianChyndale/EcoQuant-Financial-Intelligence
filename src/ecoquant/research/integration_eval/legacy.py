"""E8 legacy baseline: prompt-only honesty score -> fixed spread formula.

Faithful reimplementation of the archival EcoQuant logic: an LLM produces a
0-100 "honesty score" from the question alone (no evidence retrieval, no
verification), and the spread is computed by the fixed formula
``(60 - score) * 2`` bps. The LLM is mocked deterministically by a seeded hash
of the question text (the real legacy system's output varied per prompt run;
the mock captures its *structure*: no evidence, no verification, no review
routing).

This is the system E8 replaces: it has no citation, no verification, and never
routes to human review.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyOutput:
    score: float  # 0-100 honesty score
    spread_bps: float  # (60 - score) * 2
    citation: None  # legacy never cites evidence
    verification: str  # always "none"
    review_status: str  # always "auto" (never routed to review)


def legacy_spread_bps(score: float) -> float:
    """The archival spread formula: (60 - score) * 2 basis points."""
    return (60.0 - score) * 2.0


def legacy_honesty_score(question: str, seed: int = 0) -> LegacyOutput:
    """Deterministic mock of the prompt-only LLM honesty score.

    The mock derives a stable 0-100 score from the question text + seed,
    capturing the legacy system's behavior: the score is a function of the
    question alone, with no evidence input.
    """
    digest = hashlib.sha256(f"{seed}:{question}".encode("utf-8")).hexdigest()
    score = 20.0 + (int(digest[:8], 16) % 61)  # 20-80 range, deterministic
    return LegacyOutput(
        score=score,
        spread_bps=legacy_spread_bps(score),
        citation=None,
        verification="none",
        review_status="auto",
    )
