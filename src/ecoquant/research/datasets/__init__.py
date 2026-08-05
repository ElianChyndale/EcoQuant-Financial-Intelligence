"""Dataset adapters for the Evidence-to-Decision research programme (E0).

Each adapter projects a frozen dataset into a ``DatasetBundle`` that separates
``PublicQueryCase`` (system-visible) from ``GoldEvaluationRecord`` (evaluator-only),
so no gold label can leak into retrieval, prompts, or threshold selection.
"""

from __future__ import annotations

from .ecoquant_corpus import ADAPTER_VERSION, DATASET_ID, load_ecoquant_corpus
from .financebench import load_financebench
from .schema import DatasetBundle, GoldEvaluationRecord, PublicQueryCase

__all__ = [
    "ADAPTER_VERSION",
    "DATASET_ID",
    "DatasetBundle",
    "GoldEvaluationRecord",
    "PublicQueryCase",
    "load_ecoquant_corpus",
    "load_financebench",
]
