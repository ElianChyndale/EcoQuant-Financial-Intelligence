"""Regression guard: non-oracle feature builders must never read gold fields.

This test fails if any feature-builder module (outside an explicitly ORACLE
namespace) imports or accesses gold relevance, gold evidence, gold pages, gold
answers, gold programs, or gold labels. It scans the calibration/verification
feature source for gold-shaped access patterns and asserts the E5 leak is not
re-introduced.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEATURE_SOURCES = [
    ROOT / "src/ecoquant/research/calibration_eval/features.py",
]

# Gold-shaped identifiers that a feature builder must never touch.
# "relevant" / "relevance" in this codebase IS the gold relevance mapping
# (EvaluatorGold.relevant_evidence) — renamed parameters do not escape the rule.
GOLD_TOKENS = (
    "gold",
    "relevant_evidence",
    "relevant_by_question",
    "relevance",
    "gold_source_ids",
    "gold_page_ids",
    "gold_block_ids",
    "gold_answer",
    "gold_program",
    "gold_label",
)


def _function_mentions_gold(path: Path, function_name: str) -> list[str]:
    """Return gold-shaped identifiers mentioned inside ONE function body."""
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    mentions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            for child in ast.walk(node):
                name = None
                if isinstance(child, ast.Name):
                    name = child.id
                elif isinstance(child, ast.Attribute):
                    name = child.attr
                elif isinstance(child, ast.arg):
                    name = child.arg
                if name is None:
                    continue
                lowered = name.lower()
                if any(token in lowered for token in GOLD_TOKENS):
                    mentions.add(name)
    return sorted(mentions)


def test_no_gold_access_in_feature_builders() -> None:
    """Feature CONSTRUCTION functions must never read gold.

    Evaluation-only functions (e.g. ``labels_from_gold``) are exempt: gold is
    legitimate for evaluation. The guard scans only feature-construction
    functions, which must be gold-free.
    """
    violations: list[str] = []
    for path in FEATURE_SOURCES:
        for function_name in ("build_features_from_retrieval",):
            mentions = _function_mentions_gold(path, function_name)
            if mentions:
                violations.append(f"{path.name}:{function_name} mentions {mentions}")
    assert not violations, (
        "GOLD-DERIVED FEATURE LEAK DETECTED. Feature builders must not read gold "
        "fields (gold relevance/evidence/answers/programs). See "
        "docs/audits/E5_GOLD_LEAKAGE_AUDIT.md. Violations: " + "; ".join(violations)
    )


def test_e5_archive_preserved() -> None:
    """The invalidated E5 result must remain archived, not deleted."""
    archived = ROOT / "artifacts/archive/invalidated/e5_gold_leakage/e5_calibration_summary.json"
    manifest = ROOT / "artifacts/archive/invalidated/e5_gold_leakage/status_manifest.json"
    assert archived.exists(), "invalidated E5 result must be preserved for auditability"
    assert manifest.exists(), "invalidation manifest missing"
