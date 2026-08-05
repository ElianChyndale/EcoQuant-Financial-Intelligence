"""E8 EcoQuant system integration evaluation.

Compares the legacy prompt-only honesty-score system against the proposed
evidence pipeline (retrieval -> verification -> calibrated confidence ->
decision gate -> signed attestation), reusing the components validated in
E1-E7. The boundary is enforced: the AI produces attestation + evidence +
confidence + review status; a deterministic gate decides next-stage approval;
the AI never sets credit spreads or financial actions.
"""

from __future__ import annotations

from .legacy import LegacyOutput, legacy_honesty_score, legacy_spread_bps

__all__ = [
    "LegacyOutput",
    "legacy_honesty_score",
    "legacy_spread_bps",
]
