"""Tests for evidence-package freeze (Phase 1.5).

Proves the freeze contract:
- same source + same builder commit -> byte-identical package -> same hash;
- changing ANY display or evidence content field -> package hash changes;
- PACKAGE_MANIFEST.json is well-formed and matches the on-disk packages;
- a future second annotator can read the frozen package (it round-trips to
  the same fields the first annotator saw).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.human_study.web.services.case_presenter import (
    base_cases,
    load_manifest,
    present_case,
)
from finvest.human_study.web.services.package_freeze import (
    build_package_manifest,
    canonical_package_bytes,
    freeze_all,
    freeze_package,
    package_sha256,
)


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    """Frozen v0.2-draft manifest + fixture cache (like the workbench)."""
    from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1
    from finvest.human_study.protocol_config import V0_2_DRAFT

    tmp = tmp_path_factory.mktemp("pkgfreeze")
    cache = tmp / "cache"
    sec = cache / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(encoding="utf-8")
    for ticker in ("aapl", "msft", "ko", "eqix", "jnj", "ups"):
        (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")
    day1 = tmp / "day1"
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1, min_cases=1, cache_dir=cache, protocol=V0_2_DRAFT)
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    return manifest, cache, day1


def _first_case(manifest: dict) -> dict:
    return next(c for c in base_cases(manifest) if "cashflow-proxy" in c["case_id"])


def test_freeze_is_deterministic(env, tmp_path: Path) -> None:
    """Same source + same builder commit -> identical package and hash."""
    manifest, cache, _day1 = env
    case = _first_case(manifest)
    out = tmp_path / "pkg"

    f1 = freeze_package(case, cache, evidence_packages_dir=out, builder_commit="abc123")
    f2 = freeze_package(case, cache, evidence_packages_dir=out, builder_commit="abc123")

    assert f1.package_sha == f2.package_sha
    assert f1.json_path.read_bytes() == f2.json_path.read_bytes()
    assert f1.package_sha == f1.sha256_path.read_text(encoding="utf-8").strip()


def test_hash_changes_when_display_content_changes(env, tmp_path: Path) -> None:
    """Changing ANY display or evidence content field changes the hash.

    We simulate a display-field change by freezing the same case from the raw
    manifest vs a manifest whose question text (a display field) was edited.
    The on-disk package hash must differ.
    """
    manifest, cache, _day1 = env
    case = _first_case(manifest)
    out = tmp_path / "pkg"

    # Freeze with the original case.
    f_orig = freeze_package(case, cache, evidence_packages_dir=out, builder_commit="abc")

    # Simulate a later edit of a display field (question wording) and re-freeze
    # to a different directory (so we compare content, not paths).
    edited = dict(case)
    edited["question"] = edited["question"] + " (reworded)"
    f_edited = freeze_package(
        edited, cache, evidence_packages_dir=tmp_path / "pkg2", builder_commit="abc",
    )

    assert f_edited.package_sha != f_orig.package_sha
    assert f_edited.json_path.read_bytes() != f_orig.json_path.read_bytes()


def test_package_covers_all_display_fields(env, tmp_path: Path) -> None:
    """The frozen package contains every field an annotator reads."""
    manifest, cache, _day1 = env
    case = _first_case(manifest)
    f = freeze_package(case, cache, evidence_packages_dir=tmp_path / "pkg", builder_commit="abc")
    raw = json.loads(f.json_path.read_text(encoding="utf-8"))

    assert raw["case_id"] == case["case_id"]
    assert raw["question"] == case["question"]
    assert "definition" in raw and "statement" in raw["definition"]
    assert "evidence_table" in raw and "rows" in raw["evidence_table"]
    assert "raw_rows" in raw  # verification gate
    assert "calculation" in raw and "inputs" in raw["calculation"]
    assert "time_version" in raw and "source_cutoff" in raw["time_version"]
    # No gold labels, no machine candidate answer.
    assert "gold_answer" not in raw
    assert "minimal_evidence_sets" not in raw


def test_manifest_matches_on_disk(env, tmp_path: Path) -> None:
    """PACKAGE_MANIFEST.json lists every frozen package with matching hash."""
    _manifest, cache, day1 = env
    out = tmp_path / "pkg"
    freeze_all(
        day1, cache, evidence_packages_dir=out, builder_commit="abc",
    )
    manifest_doc = build_package_manifest(out, builder_commit="abc")

    assert manifest_doc["package_count"] == len(list(out.iterdir()))
    by_id = {p["case_id"]: p for p in manifest_doc["packages"]}
    assert len(by_id) == manifest_doc["package_count"]
    for p in manifest_doc["packages"]:
        json_path = out / p["case_id"] / f"package-{p['package_version']}.json"
        assert json_path.exists()
        assert p["package_sha256"] == hash_file(json_path)
        assert p["builder_commit"] == "abc"


def test_second_annotator_reads_same_package(env, tmp_path: Path) -> None:
    """A second annotator reads the frozen package, and it matches what the
    first annotator's presenter produced (no drift between dynamic and frozen).
    """
    manifest, cache, _day1 = env
    case = _first_case(manifest)
    f = freeze_package(case, cache, evidence_packages_dir=tmp_path / "pkg", builder_commit="abc")
    frozen = json.loads(f.json_path.read_text(encoding="utf-8"))

    # Re-present the same case from source (what a fresh annotator session does).
    presented = present_case(case, cache)
    assert frozen["question"] == presented["question"]
    assert frozen["raw_rows"] == presented["raw_rows"]
    assert frozen["evidence_table"] == presented["evidence_table"]
    assert frozen["time_version"] == presented["time_version"]


def test_canonical_bytes_stable(env) -> None:
    """canonical_package_bytes is deterministic regardless of dict ordering."""
    import json as _json

    pkg = {"b": 2, "a": [1, {"y": None, "x": "z"}]}
    b1 = canonical_package_bytes(pkg)
    reordered = {"a": [1, {"x": "z", "y": None}], "b": 2}
    b2 = canonical_package_bytes(reordered)
    assert b1 == b2
    # sha256 of canonical bytes is the package hash for a minimal package.
    assert package_sha256(pkg) == package_sha256(reordered)


def hash_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
