"""E2 table and numerical reasoning over real environmental tables (GRI-QA quant).

This package adapts the GRI-QA quant dataset, implements deterministic
calculation of the six question functions with unit handling, and compares
table-only / long-context / proposed retrieval pipelines with numeric metrics.
"""

from __future__ import annotations

from .griqa import GriqaBundle, GriqaTable, TableQuestion, load_griqa_quant

__all__ = [
    "GriqaBundle",
    "GriqaTable",
    "TableQuestion",
    "load_griqa_quant",
]
