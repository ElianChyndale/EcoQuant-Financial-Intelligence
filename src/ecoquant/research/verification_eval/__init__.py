"""E4 citation and evidence verification.

Adds a multi-layer claim verifier (citation, number grounding, year/unit/scale,
calculation reproducibility, conflict detection) with four output states, and
a benchmark measuring supported-answer accuracy and the critical false-pass
rate (unsupported answers wrongly accepted).
"""

from __future__ import annotations

from .verifier import ClaimInput, VerificationResult, verify_claim

__all__ = [
    "ClaimInput",
    "VerificationResult",
    "verify_claim",
]
