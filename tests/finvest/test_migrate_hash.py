"""Tests for the N-4 hash migration script (append-only correction).

The migration must:
- detect a legacy 16-hex evidence_package_hash that does not match the frozen
  package's authoritative full-package SHA-256;
- append (never overwrite) a round+1 correction record carrying the
  authoritative hash;
- leave already-authoritative records untouched;
- be idempotent: running twice appends nothing the second time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.migrate_evidence_package_hash import (
    authoritative_package_hash,
    migrate,
)


@pytest.fixture()
def fake_env(tmp_path: Path) -> tuple[Path, Path]:
    day1 = tmp_path / "day1"
    pkgs = tmp_path / "packages"
    day1.mkdir(parents=True)
    case = "finvest-AAPL-cashflow-proxy-2024"
    case_dir = pkgs / case
    case_dir.mkdir(parents=True)
    (case_dir / "package-1.0.sha256").write_text(
        "204a6f6d4cd37eea85a309c07bc7dbb00244903e3d8caa613f6d10e20246e8fb\n",
        encoding="utf-8",
    )
    # One legacy-hash record (round 1), one already-authoritative record (round 2).
    recs = [
        {"case_id": case, "evidence_package_hash": "d3fad0b12bf48191",
         "annotation_round": 1, "reviewer_id": "ELIAN_PRIMARY", "status": "SOLO_PROVISIONAL"},
        {"case_id": "finvest-KO-cashflow-proxy-2024", "evidence_package_hash": "x" * 64,
         "annotation_round": 2, "reviewer_id": "ELIAN_PRIMARY", "status": "SOLO_PROVISIONAL"},
    ]
    (day1 / "SOLO_ANNOTATIONS.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in recs) + "\n",
        encoding="utf-8",
    )
    # Second case needs a matching authoritative package.
    ko = pkgs / "finvest-KO-cashflow-proxy-2024"
    ko.mkdir(parents=True)
    (ko / "package-1.0.sha256").write_text("x" * 64 + "\n", encoding="utf-8")
    return day1, pkgs


def test_authoritative_hash_read(tmp_path: Path) -> None:
    case_dir = tmp_path / "packages" / "c1"
    case_dir.mkdir(parents=True)
    (case_dir / "package-1.0.sha256").write_text("abc123\n", encoding="utf-8")
    assert authoritative_package_hash(tmp_path / "packages", "c1") == "abc123"


def test_migrate_appends_correction_not_overwrite(fake_env) -> None:
    day1, pkgs = fake_env
    before = (day1 / "SOLO_ANNOTATIONS.jsonl").read_text(encoding="utf-8")
    report = migrate(day1_dir=day1, packages_dir=pkgs, dry_run=True)
    # dry-run must not touch the file.
    assert (day1 / "SOLO_ANNOTATIONS.jsonl").read_text(encoding="utf-8") == before
    assert report["n_stale_hashes"] == 1

    report = migrate(day1_dir=day1, packages_dir=pkgs, dry_run=False)
    assert report["n_appended"] == 1
    lines = (day1 / "SOLO_ANNOTATIONS.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # original 2 + 1 correction

    latest = json.loads(lines[-1])
    assert latest["case_id"] == "finvest-AAPL-cashflow-proxy-2024"
    assert latest["evidence_package_hash"] == (
        "204a6f6d4cd37eea85a309c07bc7dbb00244903e3d8caa613f6d10e20246e8fb"
    )
    assert latest["annotation_round"] == 2
    assert latest["annotation_provenance"] == "N4_HASH_MIGRATION"
    # The KO record (already authoritative) must NOT get a correction.
    assert lines[1].count("finvest-KO") and "x" * 64 in lines[1]


def test_migrate_idempotent(fake_env) -> None:
    day1, pkgs = fake_env
    migrate(day1_dir=day1, packages_dir=pkgs, dry_run=False)
    report = migrate(day1_dir=day1, packages_dir=pkgs, dry_run=False)
    assert report["n_appended"] == 0, "second run must append nothing"
    lines = (day1 / "SOLO_ANNOTATIONS.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
