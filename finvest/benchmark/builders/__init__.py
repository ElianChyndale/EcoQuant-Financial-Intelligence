"""FinVEST-Bench case builders (AI-generated candidates; human-verified gold).

Each builder produces ``FinVestCase`` records with requirement graphs, evidence
items, calculation programs, and version relations. Candidate labels are NOT
human gold until the annotation pipeline verifies them.
"""

from __future__ import annotations

from .sec_cases import BuiltCases, build_sec_cases

__all__ = ["BuiltCases", "build_sec_cases"]
