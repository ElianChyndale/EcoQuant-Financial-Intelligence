"""Uncertainty feature vectors consumed by calibration and conformal modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UncertaintyFeatures:
    """Five calibration features extracted per prediction instance."""

    retrieval_margin: float
    cross_retriever_agreement: float
    extraction_confidence: float
    temporal_validity: float
    evidence_coverage: float
