"""E1 retrieval evaluation over real datasets (FinanceBench + EcoQuant corpus).

This module builds retrievable evidence corpora from dataset bundles, runs sparse /
dense / hybrid baselines, and reports company-clustered bootstrap CIs. It reuses the
retrieval contracts from ``ecoquant.retrieval`` so the existing provenance and
fingerprint discipline applies.
"""

from __future__ import annotations

from .corpora import build_ecoquant_corpus, build_financebench_corpus

__all__ = [
    "build_ecoquant_corpus",
    "build_financebench_corpus",
]
