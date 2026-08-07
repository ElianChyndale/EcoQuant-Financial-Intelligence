"""N-4 migration: record the authoritative full-package SHA-256 in annotations.

Problem (audit N-4): the 20 solo annotation records carry a LEGACY 16-hex
truncated source-row hash as `evidence_package_hash` (e.g. d3fad0b12bf48191),
NOT the Phase-1.5 full-package SHA-256 (e.g. 204a6f6d…46e8fb) that
`package_freeze.package_hash_for_case()` computes and that each frozen package
persists as package-v1.sha256. A second annotator therefore cannot verify
byte-for-byte package replay against the recorded hash.

Fix (append-only, never overwrite): for every case whose latest annotation
record's evidence_package_hash does not match the frozen package's authoritative
hash, append a round+1 correction record that copies the latest record's
judgement fields and sets evidence_package_hash to the authoritative full-package
hash. `latest_annotation()` then returns the corrected record.

Authoritative source: human_review/evidence_packages/<case_id>/package-1.0.sha256.
Requires only the frozen packages (no SEC cache), so it runs offline in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from finvest.human_study.solo_records import load_annotations
DAY1 = ROOT / "human_review/day1/v0.2-draft"
PACKAGES = ROOT / "human_review/evidence_packages"


def authoritative_package_hash(packages_dir: Path, case_id: str) -> str | None:
    """Read the frozen package's authoritative full-package SHA-256."""
    case_dir = packages_dir / case_id
    sha_files = sorted(case_dir.glob("*.sha256")) if case_dir.exists() else []
    if not sha_files:
        return None
    return sha_files[0].read_text(encoding="utf-8").strip().split()[0]


def latest_records(day1_dir: Path) -> dict[str, dict]:
    """case_id -> most recent annotation record (append-only)."""
    out: dict[str, dict] = {}
    for rec in load_annotations(day1_dir / "SOLO_ANNOTATIONS.jsonl"):
        if "case_id" not in rec:
            continue
        out[rec["case_id"]] = rec  # later records overwrite earlier (append-only)
    return out


def migrate(day1_dir: Path = DAY1, packages_dir: Path = PACKAGES, *, dry_run: bool = False) -> dict:
    """Append round+1 correction records for stale hashes. Returns a report."""
    latest = latest_records(day1_dir)
    target = day1_dir / "SOLO_ANNOTATIONS.jsonl"
    n_stale = 0
    n_missing_package = 0
    corrected: list[str] = []

    additions: list[dict] = []
    for case_id, rec in sorted(latest.items()):
        auth = authoritative_package_hash(packages_dir, case_id)
        if auth is None:
            n_missing_package += 1
            continue
        current = (rec.get("evidence_package_hash") or "").lower()
        if current == auth:
            continue  # already authoritative
        n_stale += 1
        corrected.append(case_id)
        fix = dict(rec)
        fix["evidence_package_hash"] = auth
        fix["annotation_round"] = int(rec.get("annotation_round", 1)) + 1
        fix["evidence_package_version"] = "1.0"
        # Mark provenance of the correction without changing the judgement.
        fix["annotation_provenance"] = "N4_HASH_MIGRATION"
        additions.append(fix)

    if not dry_run and additions:
        with target.open("a", encoding="utf-8") as handle:
            for fix in additions:
                handle.write(json.dumps(fix, sort_keys=True, default=str) + "\n")

    return {
        "n_cases_latest": len(latest),
        "n_stale_hashes": n_stale,
        "n_missing_package": n_missing_package,
        "n_appended": len(additions),
        "dry_run": dry_run,
        "corrected_case_ids": corrected,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, no append")
    args = parser.parse_args()
    print(json.dumps(migrate(dry_run=args.dry_run), indent=2, sort_keys=True))
