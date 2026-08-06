"""Freeze Self-Contained Human Evidence Packages for all annotated cases.

Persists the COMPLETE evidence package (question, definition, evidence table,
raw rows, calculation inputs, time/version card) per case so a second annotator
reads byte-for-byte the same page a first annotator saw.

Usage:
    python scripts/freeze_evidence_packages.py --day1 human_review/day1/v0.2-draft \\
        --cache research/cache --out human_review/evidence_packages \\
        --commit <git-sha> [--manifest human_review/PACKAGE_MANIFEST.json]

Writes:
    <out>/<case_id>/package-v1.json   canonical package JSON
    <out>/<case_id>/package-v1.md     rendered page
    <out>/<case_id>/package-v1.sha256 full-package sha256
    <manifest>                        PACKAGE_MANIFEST.json (all packages)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _git_head(root: Path) -> str:
    """Current commit sha (short) of the repo, or 'unknown' if unavailable."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day1", type=Path, default=ROOT / "human_review/day1/v0.2-draft")
    parser.add_argument("--cache", type=Path, default=ROOT / "research/cache")
    parser.add_argument("--out", type=Path, default=ROOT / "human_review/evidence_packages")
    parser.add_argument("--manifest", type=Path, default=ROOT / "human_review/PACKAGE_MANIFEST.json")
    parser.add_argument("--commit", default=None, help="builder commit sha (default: git HEAD)")
    args = parser.parse_args()

    from finvest.human_study.web.services.package_freeze import (
        build_package_manifest, freeze_all,
    )

    commit = args.commit or _git_head(ROOT)
    freezes = freeze_all(
        args.day1, args.cache,
        evidence_packages_dir=args.out, builder_commit=commit,
    )
    manifest = build_package_manifest(args.out, builder_commit=commit)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Froze {len(freezes)} packages under {args.out}")
    print(f"Manifest: {args.manifest} ({manifest['package_count']} packages, "
          f"builder_commit={commit})")
    for f in freezes[:5]:
        print(f"  {f.case_id}: {f.package_sha[:16]}…")
    if len(freezes) > 5:
        print(f"  … and {len(freezes) - 5} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
