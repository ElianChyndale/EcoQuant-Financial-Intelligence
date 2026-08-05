"""E7 cross-domain commercial analysis over SEC XBRL facts.

Applies the evidence-to-decision method to commercial underwriting: resolves
financial metrics from real SEC XBRL facts (with traceable source IDs), computes
deterministic ratios, separates facts/inferences/assumptions, and reports
evidence sufficiency. Reuses the E3 SEC adapter.
"""

from __future__ import annotations

from .concepts import METRIC_CONCEPTS, ResolvedValue, resolve_concept

__all__ = [
    "METRIC_CONCEPTS",
    "ResolvedValue",
    "resolve_concept",
]
