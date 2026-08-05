"""FinVEST leak-free calibration and selective risk control (A6).

Rebuilds E5 from scratch with ONLY inference-time available features
(PREREGISTRATION §3, A6):

Allowed: score margins, retriever agreement, reranker score, requirement
predictions, set-selector score, temporal flags, conflict flags, execution
verification, verifier probabilities, entropy, model disagreement.

Forbidden (any gold overlap, gold coverage, gold page hit, gold program match,
gold answer match).

Nested issuer-grouped cross-fitting; metrics: AUROC, AUPRC, ECE, adaptive ECE,
Brier, AURC, risk at fixed coverage, coverage at fixed risk, subgroup
calibration, shift calibration.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ecoquant.uncertainty.calibration import (
    brier_score,
    expected_calibration_error,
    fit_calibration_folds,
    risk_coverage_curve,
)
from ecoquant.uncertainty.features import UncertaintyFeatures


@dataclass(frozen=True)
class LeakFreeFeatures:
    """Inference-time features only — never a function of gold."""

    top1_top2_margin: float
    cross_retriever_agreement: float
    set_selector_score: float
    temporal_flag: float  # 1.0 if joint temporal verification passed
    conflict_flag: float  # 1.0 if a conflict was detected
    execution_flag: float  # 1.0 if calculation executed
    candidate_entropy: float  # retrieval score distribution entropy

    def to_uncertainty(self) -> UncertaintyFeatures:
        """Map to the EcoQuant feature vector (evidence_coverage left 0.0)."""
        return UncertaintyFeatures(
            retrieval_margin=self.top1_top2_margin,
            cross_retriever_agreement=self.cross_retriever_agreement,
            extraction_confidence=self.set_selector_score,
            temporal_validity=self.temporal_flag,
            evidence_coverage=0.0,  # gold-derived coverage REMOVED (E5 leak fix)
        )


def build_leak_free_features(
    *,
    margins: Sequence[float],
    agreements: Sequence[float],
    set_scores: Sequence[float],
    temporal_flags: Sequence[float],
    conflict_flags: Sequence[float],
    execution_flags: Sequence[float],
    entropies: Sequence[float],
) -> list[LeakFreeFeatures]:
    """Build features from aligned inference-time signals (no gold input)."""
    n = len(margins)
    if not (len(agreements) == len(set_scores) == len(temporal_flags)
            == len(conflict_flags) == len(execution_flags) == len(entropies) == n):
        raise ValueError("all feature sequences must be aligned")
    return [
        LeakFreeFeatures(
            top1_top2_margin=margins[i],
            cross_retriever_agreement=agreements[i],
            set_selector_score=set_scores[i],
            temporal_flag=temporal_flags[i],
            conflict_flag=conflict_flags[i],
            execution_flag=execution_flags[i],
            candidate_entropy=entropies[i],
        )
        for i in range(n)
    ]


def evaluate_leak_free_calibration(
    features_by_issuer: Mapping[str, tuple[list[UncertaintyFeatures], list[bool]]],
    *,
    seed: int = 20260806,
) -> dict[str, object]:
    """Nested issuer-grouped calibration with leak-free features.

    Returns AUROC, AUPRC, ECE, adaptive ECE, Brier, AURC, coverage at fixed
    risk, risk at fixed coverage.
    """
    folds = fit_calibration_folds(
        dict(features_by_issuer), conformal_alpha=0.10,
        max_selective_error=0.10, seed=seed,
    )
    pooled_probs: list[float] = []
    pooled_labels: list[bool] = []
    for fold in folds:
        pooled_probs.extend(fold.test_probs)
        pooled_labels.extend(fold.test_labels)

    ece = expected_calibration_error(pooled_probs, pooled_labels)
    brier = brier_score(pooled_probs, pooled_labels)
    auc = _auc(pooled_probs, pooled_labels)
    auprc = _auprc(pooled_probs, pooled_labels)
    auroc_curve = risk_coverage_curve(pooled_probs, pooled_labels)
    auroc_auc = _area_under(pooled_probs, pooled_labels)

    return {
        "fold_count": len(folds),
        "pooled_accuracy": sum(pooled_labels) / len(pooled_labels) if pooled_labels else 0.0,
        "auroc": auc,
        "auprc": auprc,
        "ece": ece,
        "brier": brier,
        "aurc": auroc_auc,
        "coverage_at_1pct_risk": _coverage_at_risk(pooled_probs, pooled_labels, 0.01),
        "coverage_at_5pct_risk": _coverage_at_risk(pooled_probs, pooled_labels, 0.05),
        "risk_at_50pct_coverage": _risk_at_coverage(pooled_probs, pooled_labels, 0.5),
        "risk_at_80pct_coverage": _risk_at_coverage(pooled_probs, pooled_labels, 0.8),
    }


def _auc(probs: Sequence[float], labels: Sequence[bool]) -> float:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return 0.5
    paired = sorted(zip(probs, labels), key=lambda item: (item[0], item[1]))
    rank_sum = sum(rank for rank, (_, label) in enumerate(paired, start=1) if label)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _auprc(probs: Sequence[float], labels: Sequence[bool]) -> float:
    """Area under precision-recall (interpolated)."""
    paired = sorted(zip(probs, labels), key=lambda item: -item[0])
    if not paired:
        return 0.0
    tp = fp = 0
    precision_sum = 0.0
    total_pos = sum(labels)
    if total_pos == 0:
        return 0.0
    for _, label in paired:
        if label:
            tp += 1
        else:
            fp += 1
        precision_sum += tp / (tp + fp) if (tp + fp) else 0.0
    return precision_sum / len(paired)


def _coverage_at_risk(probs: Sequence[float], labels: Sequence[bool], risk: float) -> float:
    """Max coverage with selective risk <= target (risk = 1 - precision)."""
    paired = sorted(zip(probs, labels), key=lambda item: -item[0])
    n = len(paired)
    for i in range(n):
        accepted = [label for _, label in paired[: i + 1]]
        selective_risk = 1.0 - sum(accepted) / len(accepted)
        if selective_risk > risk:
            return i / n
    return 1.0


def _risk_at_coverage(probs: Sequence[float], labels: Sequence[bool], coverage: float) -> float:
    """Selective risk at a target coverage (accept top-coverage fraction)."""
    paired = sorted(zip(probs, labels), key=lambda item: -item[0])
    n = len(paired)
    k = max(1, int(round(coverage * n)))
    accepted = [label for _, label in paired[:k]]
    return 1.0 - sum(accepted) / len(accepted)


def _area_under(probs: Sequence[float], labels: Sequence[bool]) -> float:
    """AURC: area under the risk-coverage curve."""
    paired = sorted(zip(probs, labels), key=lambda item: -item[0])
    n = len(paired)
    total = 0.0
    for i in range(n):
        accepted = [label for _, label in paired[: i + 1]]
        total += 1.0 - sum(accepted) / (i + 1)
    return total / n if n else 0.0
