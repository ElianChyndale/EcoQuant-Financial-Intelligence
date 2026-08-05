"""FinVEST set-selection baselines + VISTA-Fin (A2).

Given retrieved candidate evidence units and a question requirement graph,
select a minimum sufficient evidence set.

Baselines:
- B1 ``top_k``: top-k by retrieval score (no requirement awareness).
- B2 ``greedy_set_cover``: iteratively pick the evidence covering the most
  uncovered requirements (predicted requirement coverage, not gold).
- B3 ``beam_search``: constrained beam over evidence subsets.
- B4 ``ilp_oracle``: ILP upper bound using GOLD coverage (explicitly ORACLE;
  never a headline result).
- P1 ``vista_fin``: requirement-graph + candidate-evidence-graph set selector
  (scaffold; learned weights are a later milestone).

Metrics (A2): Set Exact Match, Minimal Set Recall, All-Required-Evidence
Recall, Set Precision, Average Set Size, Redundancy, Minimality Violation.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from finvest.benchmark.schemas import RequirementGraph


@dataclass(frozen=True)
class SelectedSet:
    evidence_ids: tuple[str, ...]
    method: str
    covered_requirements: frozenset[str] = frozenset()
    is_oracle: bool = False


@dataclass(frozen=True)
class CoverageModel:
    """Predicted evidence->requirement coverage (inference-time available)."""

    # evidence_id -> set of requirement node ids it is predicted to cover.
    coverage: Mapping[str, frozenset[str]]

    def uncovered(self, selected: Sequence[str], requirements: frozenset[str]) -> frozenset[str]:
        covered = set()
        for eid in selected:
            covered |= self.coverage.get(eid, frozenset())
        return requirements - covered


def b1_top_k(
    ranked: Sequence[str],
    *,
    k: int,
) -> SelectedSet:
    """B1: top-k by retrieval score (no requirement awareness)."""
    return SelectedSet(tuple(ranked[:k]), method="b1_top_k")


def b2_greedy_set_cover(
    ranked: Sequence[str],
    requirements: frozenset[str],
    coverage: CoverageModel,
    *,
    max_size: int = 6,
) -> SelectedSet:
    """B2: greedy predicted-requirement set cover."""
    selected: list[str] = []
    remaining = set(requirements)
    candidates = list(ranked)
    while remaining and len(selected) < max_size and candidates:
        # Pick the candidate covering the most still-uncovered requirements.
        best_idx = max(
            range(len(candidates)),
            key=lambda i: len(
                coverage.coverage.get(candidates[i], frozenset()) & remaining
            ),
        )
        best = candidates.pop(best_idx)
        newly = coverage.coverage.get(best, frozenset()) & remaining
        if not newly:
            break  # no candidate covers remaining requirements
        selected.append(best)
        remaining -= newly
    return SelectedSet(
        tuple(selected),
        method="b2_greedy_set_cover",
        covered_requirements=frozenset(requirements) - remaining,
    )


def b3_beam_search(
    ranked: Sequence[str],
    requirements: frozenset[str],
    coverage: CoverageModel,
    *,
    beam: int = 4,
    max_size: int = 6,
) -> SelectedSet:
    """B3: beam search maximizing covered requirements, minimizing size."""
    candidates = ranked[:20]
    beams: list[tuple[str, ...]] = [()]
    for _ in range(max_size):
        next_beams: list[tuple[str, ...]] = []
        for subset in beams:
            for eid in candidates:
                if eid in subset:
                    continue
                next_beams.append(subset + (eid,))
        # Score: covered count (primary), smaller size (secondary).
        def _score(subset: tuple[str, ...]) -> tuple[int, int]:
            covered = set()
            for eid in subset:
                covered |= coverage.coverage.get(eid, frozenset())
            return (len(covered & requirements), -len(subset))

        beams = sorted(set(next_beams), key=_score, reverse=True)[:beam]
        if not beams:
            break
    best = max(beams, key=_score)
    covered = set()
    for eid in best:
        covered |= coverage.coverage.get(eid, frozenset())
    return SelectedSet(
        best, method="b3_beam_search",
        covered_requirements=frozenset(requirements) & frozenset(covered),
    )


def b4_ilp_oracle(
    ranked: Sequence[str],
    requirements: frozenset[str],
    gold_coverage: CoverageModel,
) -> SelectedSet:
    """B4: ILP oracle upper bound using GOLD coverage. ORACLE — not headline."""
    candidates = list(ranked)
    best_subset: tuple[str, ...] = ()
    best_covered: frozenset[str] = frozenset()
    for size in range(1, min(6, len(candidates)) + 1):
        for subset in itertools.combinations(candidates, size):
            covered = set()
            for eid in subset:
                covered |= gold_coverage.coverage.get(eid, frozenset())
            if len(covered & requirements) > len(best_covered):
                best_covered = frozenset(covered & requirements)
                best_subset = subset
    return SelectedSet(
        best_subset, method="b4_ilp_oracle",
        covered_requirements=best_covered, is_oracle=True,
    )


def vista_fin_selector(
    ranked: Sequence[str],
    requirements: RequirementGraph,
    coverage: CoverageModel,
    *,
    max_size: int = 6,
) -> SelectedSet:
    """P1: VISTA-Fin graph set selector (scaffold).

    Full implementation (requirement-graph encoder, candidate-evidence-graph
    encoder, cross-graph attention, set-level sufficiency head) is a later
    milestone with learned weights. This scaffold uses greedy set cover over
    the requirement graph's mandatory nodes — a deterministic proxy that
    preserves the interface.
    """
    mandatory = frozenset(
        n.node_id for n in requirements.nodes
        if n.node_type in {"ENTITY", "METRIC", "PERIOD", "INTERMEDIATE_VALUE"}
    )
    return b2_greedy_set_cover(
        ranked, mandatory, coverage, max_size=max_size,
    )


def set_metrics(
    selected: SelectedSet,
    gold_evidence: frozenset[str],
    gold_minimal: frozenset[str],
    requirements: frozenset[str],
    coverage: CoverageModel,
) -> dict[str, float]:
    """A2 metrics for one selected set."""
    selected_set = set(selected.evidence_ids)
    exact_match = 1.0 if selected_set == set(gold_evidence) else 0.0
    minimal_recall = len(selected_set & gold_minimal) / len(gold_minimal) if gold_minimal else 0.0
    all_required = len(selected_set & gold_evidence) / len(gold_evidence) if gold_evidence else 0.0
    precision = len(selected_set & gold_evidence) / len(selected_set) if selected_set else 0.0
    # Minimality violation: gold evidence NOT in the selected set but
    # requirements still uncovered.
    uncovered = coverage.uncovered(selected.evidence_ids, requirements)
    minimality_violation = 1.0 if uncovered else 0.0
    return {
        "set_exact_match": exact_match,
        "minimal_set_recall": minimal_recall,
        "all_required_evidence_recall": all_required,
        "set_precision": precision,
        "average_set_size": float(len(selected_set)),
        "redundancy": 1.0 - (len(selected_set) / len(selected.evidence_ids)) if selected.evidence_ids else 0.0,
        "minimality_violation_rate": minimality_violation,
    }
