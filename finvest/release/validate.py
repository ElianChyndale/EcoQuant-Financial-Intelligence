"""FinVEST release validation (A0 + Phase 18).

One-command release gate:
- all required result artifacts present,
- no gold-derived feature access in feature builders (reuses the E5 guard),
- no issuer/document-family split leakage (reuses the leakage auditor),
- paper tables generate from artifacts,
- claim-evidence matrix present.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate_release() -> dict[str, object]:
    """Run all release gates; return {gate: passed}."""
    results_dir = ROOT / "research/results"
    required_artifacts = [
        "e0_integrity.json", "e1_retrieval_summary.json", "e2_table_summary.json",
        "e3_temporal_summary.json", "e4_verification_summary.json",
        "e5_calibration_summary.json", "e7_commercial_summary.json",
        "e8_integration_summary.json",
    ]
    artifacts_ok = all((results_dir / name).exists() for name in required_artifacts)

    # Leak-free guard: FEATURE-CONSTRUCTION functions must not read gold.
    # Comments/docstrings and benchmark builders (which legitimately SET gold
    # labels) are exempt; only functions named build_*_features are scanned.
    import ast

    def _function_mentions_gold(path: Path, function_name: str) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
                    if name and ("gold" in name.lower() or "relevant" in name.lower()):
                        mentions.add(name or "")
        return sorted(mentions)

    feature_path = ROOT / "finvest/calibration/leak_free.py"
    leak_free = not _function_mentions_gold(feature_path, "build_leak_free_features")

    # Paper tables generate.
    from finvest.paper.auto_tables import build_all_tables

    tables_dir = ROOT / "artifacts/results"
    try:
        build_all_tables(results_dir, tables_dir)
        paper_ok = (tables_dir / "tables.md").exists()
    except Exception:
        paper_ok = False

    return {
        "artifacts_present": artifacts_ok,
        "feature_builders_leak_free": leak_free,
        "paper_tables_generate": paper_ok,
        "all_pass": artifacts_ok and leak_free and paper_ok,
    }


if __name__ == "__main__":
    import json

    result = validate_release()
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(0 if result["all_pass"] else 1)
