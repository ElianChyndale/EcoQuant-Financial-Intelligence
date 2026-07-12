"""Integration tests for the EcoQuant research release.

Verifies that the seven required artifacts produced by ``scripts/run_research.py``
exist and have correct structure. These tests run against the fixture-mode output
in ``research/results/`` which must be regenerated before running.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

RESULTS_DIR = Path(__file__).resolve().parents[2] / "research" / "results"

_EXPECTED_METHODS = {
    "bm25",
    "dense",
    "static_kg",
    "temporal_kg",
    "temporal_kg_rerank",
    "temporal_kg_verify",
}

_EXPECTED_ARTIFACTS = {
    "retrieval_results.csv",
    "retrieval_summary.json",
    "calibration_results.csv",
    "risk_coverage.csv",
    "valuation_sensitivity.csv",
    "risk_attestation_fixture.json",
    "manifest.json",
}


def _load_json(name: str) -> dict:
    path = RESULTS_DIR / name
    assert path.exists(), f"Missing results file: {path}"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_csv(name: str) -> list[dict]:
    path = RESULTS_DIR / name
    assert path.exists(), f"Missing results file: {path}"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------------------
# Artifact existence
# ---------------------------------------------------------------------------


class TestArtifactExistence:
    """All seven required artifacts must exist."""

    def test_all_artifacts_present(self) -> None:
        existing = {f.name for f in RESULTS_DIR.iterdir() if f.is_file()}
        missing = _EXPECTED_ARTIFACTS - existing
        assert not missing, f"Missing artifacts: {missing}"


# ---------------------------------------------------------------------------
# manifest.json
# ---------------------------------------------------------------------------


class TestManifest:
    """The manifest records run parameters and artifact hashes."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.manifest = _load_json("manifest.json")

    def test_has_seed(self) -> None:
        assert isinstance(self.manifest["seed"], int)

    def test_has_mode(self) -> None:
        assert self.manifest["mode"] in ("fixture", "production")

    def test_has_methods(self) -> None:
        assert set(self.manifest["methods"]) == _EXPECTED_METHODS

    def test_has_git_commit(self) -> None:
        assert isinstance(self.manifest["git_commit"], str)
        assert len(self.manifest["git_commit"]) >= 7

    def test_has_artifact_hashes(self) -> None:
        hashes = self.manifest["artifact_hashes"]
        assert isinstance(hashes, dict)
        assert len(hashes) >= 7

    def test_has_conformal_config(self) -> None:
        assert "conformal_alpha" in self.manifest
        assert "frozen_threshold" in self.manifest

    def test_has_dependency_versions(self) -> None:
        assert isinstance(self.manifest["dependency_versions"], dict)

    def test_has_valuation_convention(self) -> None:
        assert "valuation_convention" in self.manifest

    def test_has_attestation_schema(self) -> None:
        assert self.manifest["attestation_schema"] == "RiskAttestationV1"


# ---------------------------------------------------------------------------
# retrieval_results.csv
# ---------------------------------------------------------------------------


class TestRetrievalResults:
    """Retrieval results must have correct structure."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.rows = _load_csv("retrieval_results.csv")

    def test_not_empty(self) -> None:
        assert len(self.rows) > 0

    def test_has_required_columns(self) -> None:
        required = {"question_id", "method", "evidence_id", "rank", "score"}
        assert required.issubset(set(self.rows[0].keys()))

    def test_all_methods_represented(self) -> None:
        methods = {row["method"] for row in self.rows}
        assert methods == _EXPECTED_METHODS


# ---------------------------------------------------------------------------
# retrieval_summary.json
# ---------------------------------------------------------------------------


class TestRetrievalSummary:
    """Retrieval summary must contain per-method metrics."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.summary = _load_json("retrieval_summary.json")

    def test_has_method_metrics(self) -> None:
        assert "method_metrics" in self.summary
        assert set(self.summary["method_metrics"].keys()) == _EXPECTED_METHODS

    def test_has_question_count(self) -> None:
        assert self.summary["question_count"] > 0


# ---------------------------------------------------------------------------
# calibration_results.csv
# ---------------------------------------------------------------------------


class TestCalibrationResults:
    """Calibration results CSV must have fold data."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.rows = _load_csv("calibration_results.csv")

    def test_not_empty(self) -> None:
        assert len(self.rows) > 0

    def test_has_required_columns(self) -> None:
        required = {"fold_id", "test_issuer"}
        assert required.issubset(set(self.rows[0].keys()))


# ---------------------------------------------------------------------------
# risk_coverage.csv
# ---------------------------------------------------------------------------


class TestRiskCoverage:
    """Risk coverage CSV must have fold data."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.rows = _load_csv("risk_coverage.csv")

    def test_not_empty(self) -> None:
        assert len(self.rows) > 0

    def test_has_required_columns(self) -> None:
        required = {"fold_id", "test_issuer", "coverage"}
        assert required.issubset(set(self.rows[0].keys()))


# ---------------------------------------------------------------------------
# valuation_sensitivity.csv
# ---------------------------------------------------------------------------


class TestValuationSensitivity:
    """Valuation sensitivity CSV must exist and have data."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.rows = _load_csv("valuation_sensitivity.csv")

    def test_not_empty(self) -> None:
        assert len(self.rows) > 0

    def test_has_required_columns(self) -> None:
        required = {"scenario", "status"}
        assert required.issubset(set(self.rows[0].keys()))


# ---------------------------------------------------------------------------
# risk_attestation_fixture.json
# ---------------------------------------------------------------------------


class TestRiskAttestationFixture:
    """Risk attestation fixture must have valid EIP-712 structure."""

    @pytest.fixture(autouse=True)
    def load(self) -> None:
        self.fixture = _load_json("risk_attestation_fixture.json")

    def test_has_attestation(self) -> None:
        assert "attestation" in self.fixture
        att = self.fixture["attestation"]
        assert att["schemaVersion"] == 1
        assert isinstance(att["assetId"], str)
        assert att["assetId"].startswith("0x")

    def test_has_signature(self) -> None:
        assert "signature" in self.fixture
        sig = self.fixture["signature"]
        assert sig.startswith("0x")
        # 65 bytes = 130 hex chars + 0x prefix = 132
        assert len(sig) == 132

    def test_has_domain_separator(self) -> None:
        assert "domainSeparator" in self.fixture
        assert self.fixture["domainSeparator"].startswith("0x")

    def test_has_recovered_provider(self) -> None:
        assert "recoveredProvider" in self.fixture
        assert self.fixture["recoveredProvider"].startswith("0x")

    def test_compiled_solidity_pending(self) -> None:
        assert self.fixture["compiledSolidityVerification"] == "PENDING_GBL_TASK_12_14"
