"""E3 temporal and contradiction-aware retrieval over SEC EDGAR XBRL facts.

This package adapts SEC companyfacts into a temporal corpus (valid time = end,
source time = filed), constructs the three required temporal question classes
(old_vs_new, amended_vs_original, cross_period), and compares retrieval
baselines with source/valid-time filtering plus contradiction detection.
"""

from __future__ import annotations

from .sec_adapter import SecBundle, SecFact, load_companyfacts

__all__ = [
    "SecBundle",
    "SecFact",
    "load_companyfacts",
]
