"""Tests for the paper-reproduction-lab adapter (Phase 5.3).

Skipped when the tool repo is not installed. Asserts:
- the emitted StudyManifest validates against the lab's Pydantic model;
- the emitted RunManifest validates and encodes headline_eligible=false;
- the manifests bind corpus/annotation/split hashes;
- write_manifests persists valid files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

paper_reproduction_lab = pytest.importorskip("paper_reproduction_lab")
from paper_reproduction_lab.models import RunManifest, StudyManifest

from integrations.reproduction_lab_adapter import (
    emit_run_manifest,
    emit_study_manifest,
    write_manifests,
)


def _sample_output() -> dict:
    return {
        "experiment": "A11_TWO_STAGE",
        "n_cases": 19,
        "decisions": {"ANSWER": 0, "REVIEW": 19, "ABSTAIN": 0},
        "corpus": {"corpus_id": "af406d47"},
        "markers": ["SOLO_PROVISIONAL", "NOT_PAPER_HEADLINE"],
    }


def test_study_manifest_valid() -> None:
    manifest = emit_study_manifest(
        _sample_output(),
        hypothesis="Leak-free retrieval + joint verification separates correct from unsupported answers",
        corpus_hash="af406d474f745547",
        rerun_command="python experiments/a11_retrieval/run.py",
    )
    # Validates against the lab's Pydantic model.
    StudyManifest(**manifest)
    assert manifest["study_id"] == "retrieval"
    assert manifest["synthetic"] is True
    assert manifest["seed"] == 42
    assert manifest["dataset_id"].startswith("finvest-corpus-")
    assert "r1-bm25" in manifest["methods"]
    assert manifest["evidence_labels"] == ["scoped-claim-check"]


def test_run_manifest_valid_and_honest() -> None:
    run = emit_run_manifest(
        [emit_study_manifest(
            _sample_output(), hypothesis="h", corpus_hash="af406d",
            rerun_command="python experiments/a11_retrieval/run.py",
        )],
        corpus_hash="af406d474f745547",
        annotation_hash="abc123",
        split_hash="split456",
    )
    RunManifest(**run)
    assert run["run_id"] == "v0-1-seed-42"
    # The release claim encodes headline_eligible=false.
    assert run["release_claim"] == "synthetic-scoped-observations-not-original-paper-results"
    assert run["dataset_hashes"]["finvest-corpus"] == "af406d474f745547"
    assert run["config_hashes"]["split"] == "split456"


def test_write_manifests_persists(tmp_path: Path) -> None:
    result = write_manifests(
        _sample_output(),
        output_dir=tmp_path / "manifests",
        corpus_hash="af406d474f745547",
        annotation_hash="abc123",
        split_hash="split456",
        hypothesis="test hypothesis",
        rerun_command="python experiments/a11_retrieval/run.py",
    )
    assert (tmp_path / "manifests" / "study-manifest.json").exists()
    assert (tmp_path / "manifests" / "run-manifest.json").exists()
    # The persisted files re-validate.
    import json

    study = json.loads((tmp_path / "manifests" / "study-manifest.json").read_text(encoding="utf-8"))
    StudyManifest(**study)
    run = json.loads((tmp_path / "manifests" / "run-manifest.json").read_text(encoding="utf-8"))
    RunManifest(**run)
