"""E5 calibration and selective prediction over real retrieval results.

Builds the five uncertainty features from retrieval results, calibrates them
with the existing Platt/conformal machinery, and evaluates selective prediction
(risk-coverage curves, coverage at precision targets) so a system can auto-accept
easy cases and abstain on hard ones with a bounded error rate.
"""

from __future__ import annotations

from .features import build_features_from_retrieval

__all__ = [
    "build_features_from_retrieval",
]
