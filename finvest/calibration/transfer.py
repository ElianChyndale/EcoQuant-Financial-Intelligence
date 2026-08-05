"""FinVEST cross-dataset transfer evaluation (A8).

Tests whether the method generalizes:
- FinVEST-trained -> external datasets (FinanceBench, GRI-QA, ...).
- External-trained -> FinVEST unseen-issuer / chronological / cross-jurisdiction.

Never merge incompatible metrics into one misleading average — report per
dataset.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransferResult:
    source: str  # "finvest-train" or an external dataset name
    target: str  # "finvest-test-a" | "finvest-test-b" | "finvest-test-c" | external
    metric_name: str
    value: float
    n_cases: int


def report_transfer(results: tuple[TransferResult, ...]) -> dict[str, object]:
    """Aggregate transfer results per (source, target) pair — no merging."""
    by_pair: dict[tuple[str, str], list[TransferResult]] = {}
    for result in results:
        by_pair.setdefault((result.source, result.target), []).append(result)
    return {
        f"{source}->{target}": {
            r.metric_name: r.value for r in pair_results
        }
        for (source, target), pair_results in sorted(by_pair.items())
    }
