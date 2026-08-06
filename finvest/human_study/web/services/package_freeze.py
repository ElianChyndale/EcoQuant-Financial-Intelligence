"""Evidence-package freeze (Phase 1.5): persist the Self-Contained Human
Evidence Package so a second annotator reads the SAME page a first annotator
saw, byte-for-byte.

Problem fixed: before this module, ``build_evidence_package`` produced the full
package at presentation time but never saved it; the annotation's
``evidence_package_hash`` was only ``raw_rows[0].source_hash[:16]`` (the hash
of one source row), so changing any display field (metric definition, human
labels, row order, time/version card wording, calculation description, page
rendering) would NOT change the recorded hash. A future second annotator could
re-derive a "similar but not identical" page and the mismatch would be
invisible.

This module freezes the COMPLETE package:

    human_review/evidence_packages/<case_id>/
        package-v1.json     canonical JSON of the whole SHEP (display + raw)
        package-v1.md       rendered markdown (the page the annotator reads)
        package-v1.sha256   sha256 of the canonical package JSON

and produces ``human_review/PACKAGE_MANIFEST.json`` listing every frozen
package with its full-package hash, builder commit, and source hashes.

Freeze contract:
    same source facts + same builder commit  -> byte-identical package
                                              -> identical hash
    any display or evidence content change   -> package hash changes
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finvest.human_study.web.services.case_presenter import (
    present_case,
    render_markdown,
)

DEFAULT_VERSION = "1.0"


def canonical_package_bytes(package: dict[str, Any]) -> bytes:
    """Canonical JSON encoding of a package (deterministic, stable across runs).

    Uses the same canonicalization convention as financial-ai-contracts
    (sort_keys, compact separators, ensure_ascii=False) so the hash is stable
    and comparable. Array order is significant (row order matters to a reader).
    """
    return json.dumps(
        package, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def package_sha256(package: dict[str, Any]) -> str:
    """Full-package sha256 hexdigest (covers every display + raw field)."""
    return hashlib.sha256(canonical_package_bytes(package)).hexdigest()


def _full_package(
    sealed_case: dict[str, Any],
    cache: Path,
    *,
    builder_commit: str,
    package_version: str = DEFAULT_VERSION,
) -> dict[str, Any]:
    """Build the COMPLETE package (display package + sealed-case provenance).

    The display fields come from ``present_case`` (which resolves source facts
    from disk and calls ``build_evidence_package``). The ``provenance`` block
    records the version-2 display+evidence contract, the builder commit, and
    the package version so a reader knows exactly which pipeline produced it.
    No gold labels or machine candidate answers are included (they stay sealed).
    """
    presented = present_case(sealed_case, cache)
    return {
        "schema_version": "finvest-evidence-package.v2",
        "package_version": package_version,
        "builder_commit": builder_commit,
        "case_id": sealed_case["case_id"],
        "question": presented["question"],
        "issuer": presented.get("issuer") or sealed_case.get("issuer_id"),
        "definition": presented["definition"],
        "evidence_table": presented["evidence_table"],
        "raw_rows": presented["raw_rows"],
        "calculation": presented["calculation"],
        "time_version": presented["time_version"],
        "provenance": {
            "source_cutoff": sealed_case.get("source_cutoff"),
            "target_fiscal_year": sealed_case.get("target_fiscal_year"),
            "target_period_end": sealed_case.get("target_period_end"),
            "answer_type": sealed_case.get("answer_type"),
            "calculation_program": sealed_case.get("calculation_program"),
            "evidence_ids": [
                it.get("evidence_id") for it in (sealed_case.get("evidence_items") or [])
            ],
        },
        "markers": ["EXPLORATORY_PILOT", "SMALL_SAMPLE", "NOT_PAPER_HEADLINE"],
    }


@dataclass(frozen=True)
class PackageFreeze:
    """A frozen evidence package on disk."""

    case_id: str
    package_dir: Path
    json_path: Path
    md_path: Path
    sha256_path: Path
    package_sha: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "package_dir": str(self.package_dir),
            "json": str(self.json_path),
            "markdown": str(self.md_path),
            "sha256": str(self.sha256_path),
            "package_sha256": self.package_sha,
        }


def package_hash_for_case(
    sealed_case: dict[str, Any],
    cache: Path,
    *,
    builder_commit: str = "runtime",
    package_version: str = DEFAULT_VERSION,
) -> str:
    """Full-package sha256 for a case WITHOUT persisting it.

    Used by annotation entry so the recorded evidence_package_hash is the hash
    of the COMPLETE package (every display + evidence field), matching what the
    freeze pipeline would persist. Deterministic: same source + same builder
    commit -> same hash.
    """
    package = _full_package(
        sealed_case, cache, builder_commit=builder_commit, package_version=package_version,
    )
    return package_sha256(package)


def freeze_package(
    sealed_case: dict[str, Any],
    cache: Path,
    *,
    evidence_packages_dir: Path,
    builder_commit: str,
    package_version: str = DEFAULT_VERSION,
) -> PackageFreeze:
    """Build and freeze one case's complete evidence package to disk.

    Writes package-v1.json (canonical), package-v1.md (rendered page), and
    package-v1.sha256. Returns the freeze descriptor. The full-package hash is
    the value a future annotation record should reference.
    """
    package = _full_package(
        sealed_case, cache, builder_commit=builder_commit, package_version=package_version,
    )
    package_sha = package_sha256(package)

    case_dir = evidence_packages_dir / sealed_case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    json_path = case_dir / f"package-{package_version}.json"
    md_path = case_dir / f"package-{package_version}.md"
    sha_path = case_dir / f"package-{package_version}.sha256"

    json_path.write_text(
        json.dumps(package, indent=2, sort_keys=True, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(_presented_from_package(package)), encoding="utf-8")
    sha_path.write_text(package_sha + "\n", encoding="utf-8")

    return PackageFreeze(
        case_id=sealed_case["case_id"],
        package_dir=case_dir,
        json_path=json_path,
        md_path=md_path,
        sha256_path=sha_path,
        package_sha=package_sha,
    )


def _presented_from_package(package: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a ``present_case``-shaped dict from the frozen package so the
    existing ``render_markdown`` can render the SAME fields the annotator saw."""
    return {
        "case_id": package["case_id"],
        "question": package["question"],
        "definition": package["definition"],
        "raw_rows": package["raw_rows"],
        "evidence_table": package["evidence_table"],
        "calculation": package["calculation"],
        "time_version": package["time_version"],
    }


def freeze_all(
    day1_dir: Path,
    cache: Path,
    *,
    evidence_packages_dir: Path,
    builder_commit: str,
    package_version: str = DEFAULT_VERSION,
) -> list[PackageFreeze]:
    """Freeze every case in QUEUE_MANIFEST + EXTENSION_40_cases.json."""
    from finvest.human_study.web.services.case_presenter import (
        load_manifest, base_cases,
    )

    sealed: dict[str, dict[str, Any]] = {}
    manifest = load_manifest(day1_dir)
    for c in base_cases(manifest):
        sealed[c["case_id"]] = c
    ext_file = day1_dir / "EXTENSION_40_cases.json"
    if ext_file.exists():
        for c in json.loads(ext_file.read_text(encoding="utf-8")):
            sealed[c["case_id"]] = c

    freezes = []
    for case_id, case in sorted(sealed.items()):
        freezes.append(
            freeze_package(
                case, cache,
                evidence_packages_dir=evidence_packages_dir,
                builder_commit=builder_commit,
                package_version=package_version,
            )
        )
    return freezes


def build_package_manifest(
    evidence_packages_dir: Path,
    *,
    builder_commit: str,
    package_version: str = DEFAULT_VERSION,
) -> dict[str, Any]:
    """Scan frozen packages and emit PACKAGE_MANIFEST.json.

    For each <case_id>/package-<version>.json, re-hash the on-disk file and
    record: package_sha256, size, source hashes (from raw_rows), and the
    builder commit. Mirrors the freeze contract: hash changes iff the package
    content changed.
    """
    packages: list[dict[str, Any]] = []
    for case_dir in sorted(p for p in evidence_packages_dir.iterdir() if p.is_dir()):
        json_path = case_dir / f"package-{package_version}.json"
        if not json_path.exists():
            continue
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        file_sha = hashlib.sha256(json_path.read_bytes()).hexdigest()
        source_hashes = [
            r.get("source_hash") for r in (raw.get("raw_rows") or []) if r.get("source_hash")
        ]
        packages.append({
            "case_id": raw.get("case_id"),
            "package_version": package_version,
            "package_sha256": file_sha,
            "file_size": json_path.stat().st_size,
            "builder_commit": raw.get("builder_commit") or builder_commit,
            "source_hashes": source_hashes,
        })
    manifest = {
        "schema_version": "finvest-evidence-package-manifest.v1",
        "builder_commit": builder_commit,
        "package_version": package_version,
        "package_count": len(packages),
        "packages": packages,
    }
    return manifest
