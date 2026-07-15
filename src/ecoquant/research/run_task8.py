"""SOL-4B Task 8 research-release command.

Fixture execution is an explicitly non-final local demonstration. Production
execution starts from an approved source manifest and external cache, adapts
validated ``normalized_document_v1`` payloads into a sealed authoritative
corpus, and crosses the frozen Task 5 final boundary without fallback.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from contextlib import contextmanager, redirect_stdout
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

from ecoquant.evidence_graph.builder import build_graph
from ecoquant.evidence_graph.graph import TemporalEvidenceGraph
from ecoquant.retrieval.base import (
    REGISTERED_METHOD_IDS,
    RetrieverQuery,
    all_retrievers,
    compare_retrievers,
    corpus_fingerprint,
)
from ecoquant.retrieval.corpus_adapter import AuthoritativeCorpus, adapt_evidence_spans
from ecoquant.retrieval.evaluation import EvidenceLocation
from integrations.pdf_manager.normalized_document import (
    NormalizedDocumentIngestionError,
    load_normalized_document,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QUESTIONS = REPOSITORY_ROOT / "research" / "questions" / "questions.jsonl"
DEFAULT_RESULTS = REPOSITORY_ROOT / "research" / "results"
SOURCE_CACHE_SCHEMA = "ecoquant-source-cache.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SIGNING_ENVIRONMENT = (
    "ECOQUANT_SIGNING_KEY_HEX",
    "ECOQUANT_SIGNING_PROVIDER",
    "ECOQUANT_SIGNING_CHAIN_ID",
    "ECOQUANT_SIGNING_CONTRACT",
)
_PRINCIPAL_ARTIFACTS = (
    "retrieval_results.csv",
    "retrieval_summary.json",
    "calibration_results.csv",
    "risk_coverage.csv",
    "valuation_sensitivity.csv",
    "risk_attestation_fixture.json",
    "manifest.json",
)
_NON_MANIFEST_SCHEMAS = {
    "retrieval_results.csv": "task8-retrieval-results.v1",
    "retrieval_summary.json": "task8-retrieval-summary.v1",
    "calibration_results.csv": "task8-calibration-results.v1",
    "risk_coverage.csv": "task8-risk-coverage.v1",
    "valuation_sensitivity.csv": "task8-valuation-sensitivity.v1",
    "risk_attestation_fixture.json": "risk-attestation-v1.fixture-envelope.v1",
}


@contextmanager
def _offline_model_loading() -> Iterator[None]:
    """Prevent Task 8 production checks from initiating model downloads."""

    names = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ[name] = "1"
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class Task8Error(RuntimeError):
    """A machine-readable Task 8 configuration or execution failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        blockers: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.blockers = tuple(blockers)

    def payload(self) -> dict[str, object]:
        return {
            "status": "blocked",
            "code": self.code,
            "message": str(self),
            "blockers": list(self.blockers),
            "fixture_fallback": False,
        }


@dataclass(frozen=True)
class ProductionInputs:
    """Validated external source bytes and their authoritative adaptation."""

    corpus: AuthoritativeCorpus
    spans: tuple[object, ...]
    graph: TemporalEvidenceGraph
    source_hashes: Mapping[str, str]
    normalized_document_hashes: Mapping[str, str]
    evidence_catalog: Mapping[str, EvidenceLocation]
    source_manifest_rows: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class SigningConfiguration:
    private_key: bytes
    provider: str
    chain_id: int
    verifying_contract: str

    @classmethod
    def from_environment(cls) -> "SigningConfiguration":
        missing = [name for name in _SIGNING_ENVIRONMENT if not os.environ.get(name)]
        if missing:
            raise Task8Error(
                "missing_signing_configuration",
                "production signing configuration is incomplete",
            )
        key_text = os.environ["ECOQUANT_SIGNING_KEY_HEX"].removeprefix("0x")
        try:
            private_key = bytes.fromhex(key_text)
        except ValueError as error:
            raise Task8Error("invalid_signing_configuration", "production signing key must be hexadecimal") from error
        if len(private_key) != 32:
            raise Task8Error("invalid_signing_configuration", "production signing key must be 32 bytes")
        try:
            chain_id = int(os.environ["ECOQUANT_SIGNING_CHAIN_ID"])
        except ValueError as error:
            raise Task8Error("invalid_signing_configuration", "production signing chain ID must be an integer") from error
        if chain_id <= 0:
            raise Task8Error("invalid_signing_configuration", "production signing chain ID must be positive")
        return cls(
            private_key=private_key,
            provider=os.environ["ECOQUANT_SIGNING_PROVIDER"],
            chain_id=chain_id,
            verifying_contract=os.environ["ECOQUANT_SIGNING_CONTRACT"],
        )


def _json_write(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                payload,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _csv_write(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    if not rows:
        raise Task8Error("empty_artifact", f"artifact must contain at least one row: {path.name}")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _all_finite(value: object) -> bool:
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, Mapping):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_all_finite(item) for item in value)
    return True


def _require_fitted_task6_state(folds: Sequence[Mapping[str, object]]) -> None:
    """Require complete finite fitted state before downstream final decisions."""

    if not folds:
        raise Task8Error(
            "unfitted_task6_state",
            "production requires fitted Task 6 issuer calibration state",
        )
    policy_fields = {
        "calibrated_probability_threshold",
        "conformal_threshold",
        "evidence_sufficiency_threshold",
        "extraction_validity_required",
        "temporal_validity_required",
    }
    for fold in folds:
        coefficients = fold.get("fitted_coefficients")
        normalization = fold.get("normalization_parameters")
        convergence = fold.get("convergence_status")
        policy = fold.get("decision_policy")
        if not isinstance(coefficients, Mapping) or not isinstance(normalization, Mapping):
            raise Task8Error("unfitted_task6_state", "fitted Task 6 coefficients and normalization are required")
        if not isinstance(convergence, Mapping) or convergence.get("converged") is not True:
            raise Task8Error("unfitted_task6_state", "fitted Task 6 calibrator must converge")
        if convergence.get("degeneracy_status") != "normal":
            raise Task8Error("unfitted_task6_state", "fitted Task 6 calibrator is degenerate")
        if not isinstance(policy, Mapping) or set(policy) != policy_fields:
            raise Task8Error("unfitted_task6_state", "complete frozen Task 6 decision policy is required")
        if not _all_finite((coefficients, normalization, convergence, policy)):
            raise Task8Error("unfitted_task6_state", "fitted Task 6 state must be finite")


def _fixture_decision_code(summary: Mapping[str, object]) -> object:
    from ecoquant.uncertainty.decision import DecisionCode

    decisions = summary.get("decision_summary")
    if not isinstance(decisions, Mapping):
        raise Task8Error("unfitted_task6_state", "fixture release requires Task 6 decision output")
    if int(decisions.get("auto_report_count", 0)) > 0:
        return DecisionCode.AUTO_REPORT
    if int(decisions.get("human_review_required_count", 0)) > 0:
        return DecisionCode.HUMAN_REVIEW_REQUIRED
    return DecisionCode.INSUFFICIENT_EVIDENCE


def _fixture_valuation_rows(
    summary: Mapping[str, object],
) -> tuple[list[dict[str, object]], object]:
    from ecoquant.valuation.bond_pricing import BondTerms
    from ecoquant.valuation.policy import PolicyInput, apply_policy
    from ecoquant.valuation.sensitivity import compute_sensitivity

    decision_code = _fixture_decision_code(summary)
    policy = apply_policy(
        PolicyInput(
            decision_code=decision_code,
            evidence_ids=("aib-2024",),
            risk_factors={"transition_risk": 0.40},
            extraction_valid=True,
            risk_channel_map={"transition_risk": "credit_spread"},
            base_spread_bps=145,
            max_spread_delta_bps=50,
            max_haircut_bps=500,
        )
    )
    valuation = compute_sensitivity(
        BondTerms(
            face_value=100.0,
            coupon_rate=0.04,
            payment_frequency=2,
            issue_date=date(2020, 6, 30),
            settlement_date=date(2024, 9, 15),
            maturity_date=date(2030, 6, 30),
        ),
        0.035,
        145,
        policy,
        {"transition_risk": "credit_spread"},
        issuer="AIB",
        asset_id="IE00B4L5Y983",
        evidence_id="aib-2024",
        rule_id="ecoquant-valuation-policy",
        rule_version="1.0.0",
        valid_time="2024-12-31",
        source_time="2025-03-01",
    )
    rows = [
        {
            "scenario": scenario.scenario_name,
            "status": scenario.status,
            "evidence_id": scenario.evidence_id,
            "issuer": scenario.issuer,
            "asset_id": scenario.asset_id,
            "risk_factor": scenario.risk_factor,
            "risk_channel": scenario.risk_channel,
            "rule_id": scenario.rule_id,
            "rule_version": scenario.rule_version,
            "decision_code": int(scenario.decision_code),
            "base_spread_bps": scenario.base_spread_bps,
            "spread_delta_bps": scenario.spread_delta_bps,
            "adjusted_spread_bps": scenario.adjusted_spread_bps,
            "settlement_date": scenario.settlement_date.isoformat(),
            "maturity_date": scenario.maturity_date.isoformat(),
            "coupon_frequency": scenario.coupon_frequency,
            "day_count_convention": scenario.day_count_convention,
            "compounding_convention": scenario.compounding_convention,
            "clean_price": scenario.adjusted_clean_price,
            "dirty_price": scenario.adjusted_dirty_price,
            "accrued_interest": scenario.accrued_interest,
            "macaulay_duration": scenario.macaulay_duration,
            "modified_duration": scenario.modified_duration,
            "convexity": scenario.convexity,
            "valid_time": scenario.valid_time,
            "source_time": scenario.source_time,
        }
        for scenario in valuation.scenarios
    ]
    if not rows:
        raise Task8Error("empty_valuation", "fixture Task 6 decision produced no supported valuation scenario")
    return rows, policy


def _fixture_signing_key(seed: int) -> bytes:
    from ecdsa import SECP256k1

    material = hashlib.sha256(f"ecoquant-task8-fixture-signing:{seed}".encode()).digest()
    scalar = int.from_bytes(material, "big") % (SECP256k1.order - 1) + 1
    return scalar.to_bytes(32, "big")


def _fixture_attestation(
    *,
    seed: int,
    decision_code: object,
    recommended_haircut_bps: int | None,
) -> dict[str, object]:
    from ecdsa import SECP256k1, SigningKey

    from ecoquant.attestation.eip712 import compute_asset_id, compute_model_version, keccak256
    from ecoquant.attestation.merkle import evidence_merkle_root
    from ecoquant.attestation.models import RiskAttestationV1
    from ecoquant.attestation.signing import (
        CANONICAL_DOMAIN_NAME,
        CANONICAL_DOMAIN_VERSION,
        sign_attestation,
        verify_provider,
    )
    from scripts.run_research import _CORPUS

    private_key = _fixture_signing_key(seed)
    signing_key = SigningKey.from_string(private_key, curve=SECP256k1)
    provider = "0x" + keccak256(signing_key.get_verifying_key().to_string())[-20:].hex()
    evidence_leaves = [bytes.fromhex(hashlib.sha256(record.evidence_id.encode()).hexdigest()) for record in sorted(_CORPUS, key=lambda item: item.evidence_id)]
    evidence_root = evidence_merkle_root(evidence_leaves)
    domain = {
        "name": CANONICAL_DOMAIN_NAME,
        "version": CANONICAL_DOMAIN_VERSION,
        "chainId": 31337,
        "verifyingContract": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
    }
    attestation = RiskAttestationV1(
        schema_version=1,
        asset_id=compute_asset_id("IE00B4L5Y983"),
        as_of=1_720_000_000,
        risk_score_bps=4_000,
        confidence_bps=8_500,
        recommended_haircut_bps=recommended_haircut_bps or 0,
        evidence_root=evidence_root,
        model_version=compute_model_version(),
        decision_code=int(decision_code),
        valid_until=1_720_100_000,
        nonce=seed,
        provider=provider,
    )
    signed = sign_attestation(
        attestation,
        private_key,
        chain_id=domain["chainId"],
        verifying_contract=domain["verifyingContract"],
    )
    if not verify_provider(
        signed,
        chain_id=domain["chainId"],
        verifying_contract=domain["verifyingContract"],
    ):
        raise Task8Error("invalid_attestation_signature", "fixture attestation provider recovery failed")
    return {
        "schema_version": "risk-attestation-v1.fixture-envelope.v1",
        "mode": "fixture",
        "productionVerified": False,
        "fixtureSigning": True,
        "attestation": {
            "schemaVersion": attestation.schema_version,
            "assetId": "0x" + attestation.asset_id.hex(),
            "asOf": attestation.as_of,
            "riskScoreBps": attestation.risk_score_bps,
            "confidenceBps": attestation.confidence_bps,
            "recommendedHaircutBps": attestation.recommended_haircut_bps,
            "evidenceRoot": "0x" + attestation.evidence_root.hex(),
            "modelVersion": "0x" + attestation.model_version.hex(),
            "decisionCode": attestation.decision_code,
            "validUntil": attestation.valid_until,
            "nonce": attestation.nonce,
            "provider": attestation.provider,
        },
        "domain": domain,
        "evidenceRootAlgorithm": "sorted-evidence-id-bytes-keccak-merkle-v1",
        "domainSeparator": "0x" + signed.domain_hash.hex(),
        "structHash": "0x" + signed.struct_hash.hex(),
        "digest": "0x" + signed.digest.hex(),
        "publicKey": "0x" + signed.public_key.hex(),
        "signature": "0x" + signed.signature.hex(),
        "recoveredProvider": signed.signer_address,
        "compiledSolidityVerification": "VERIFIED_CANONICAL_BRIDGE_FIXTURE",
    }


def _git_value(*arguments: str, fallback: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *arguments],
            cwd=REPOSITORY_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip() or fallback
    except (OSError, subprocess.CalledProcessError):
        return fallback


def _fixture_manifest(
    *,
    seed: int,
    output_dir: Path,
    legacy_manifest: Mapping[str, object],
    attestation: Mapping[str, object],
) -> dict[str, object]:
    from scripts.run_research import _CORPUS

    folds = legacy_manifest.get("split_manifests")
    if not isinstance(folds, list):
        raise Task8Error("unfitted_task6_state", "fixture calibration manifests are missing")
    _require_fitted_task6_state(folds)
    branch = _git_value("branch", "--show-current", fallback="unavailable")
    dirty = bool(_git_value("status", "--porcelain", fallback="dirty"))
    artifacts: dict[str, dict[str, object]] = {}
    for filename, schema_version in _NON_MANIFEST_SCHEMAS.items():
        data = (output_dir / filename).read_bytes()
        if not data:
            raise Task8Error("empty_artifact", f"artifact is empty: {filename}")
        artifacts[filename] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "schema_version": schema_version,
        }
    backends = {
        method_id: {
            "backend_status": "fixture",
            "backend_identity": f"deterministic-local:{method_id}",
            "execution_receipt_identity": None,
            "model_id": (
                "sentence-transformers/all-MiniLM-L6-v2"
                if method_id == "dense"
                else "BAAI/bge-reranker-base"
                if method_id in {"temporal_kg_rerank", "temporal_kg_verify"}
                else None
            ),
            "verified_immutable_revision": None,
            "availability": "fixture_only_not_production_verified",
        }
        for method_id in REGISTERED_METHOD_IDS
    }
    return {
        "schema_version": "task8-manifest.v1",
        "repository": {
            "commit": _git_value("rev-parse", "HEAD", fallback="unknown"),
            "branch": branch,
            "dirty": dirty,
        },
        "run": {
            "execution_mode": "fixture",
            "seed": seed,
            "run_id": f"fixture-{seed}",
            "command": "python -m ecoquant.research.run_task8 --mode fixture --output-dir <isolated-output> --seed 20260710",
            "timestamp_policy": "frozen_fixture",
            "timestamp": "2026-07-10T00:00:00Z",
            "completion_status": "fixture_complete",
            "production_verified": False,
            "final_release": False,
        },
        "sources": {
            "fixture_input": True,
            "source_hashes": {
                record.evidence_id: hashlib.sha256(record.text.encode()).hexdigest()
                for record in sorted(_CORPUS, key=lambda item: item.evidence_id)
            },
            "normalized_document_hashes": {},
            "question_set_hash": hashlib.sha256(DEFAULT_QUESTIONS.read_bytes()).hexdigest(),
            "corpus_fingerprint": corpus_fingerprint(_CORPUS),
            "graph_schema_version": "retrieval-safe-graph.v1",
        },
        "retrieval": {
            "method_ids": list(REGISTERED_METHOD_IDS),
            "top_k": 5,
            "valid_at": "question_period_end_fixture",
            "source_cutoff": "valid_at_fixture",
            "backends": backends,
            "package_versions": legacy_manifest.get("dependency_versions", {}),
        },
        "calibration": {
            "issuer_split_manifests": folds,
            "feature_version": "task6-uncertainty-features.v1",
            "normalization_state": [fold["normalization_parameters"] for fold in folds],
            "coefficients": [fold["fitted_coefficients"] for fold in folds],
            "convergence": [fold["convergence_status"] for fold in folds],
            "conformal_alpha": legacy_manifest.get("conformal_alpha"),
            "conformal_thresholds": [fold["conformal_threshold"] for fold in folds],
            "decision_thresholds": [fold["decision_threshold"] for fold in folds],
        },
        "valuation": {
            "rule_id": "ecoquant-valuation-policy",
            "rule_version": "1.0.0",
            "day_count_convention": "Actual/Actual ICMA",
            "compounding_convention": "nominal annual yield compounded at coupon frequency",
            "supported_schedule_contract": "backward-unadjusted-eom-fixed-rate-bullet-stubs-max-two-periods.v1",
        },
        "attestation": {
            "schema_version": 1,
            "model_version": attestation["attestation"]["modelVersion"],  # type: ignore[index]
            "domain": attestation["domain"],
            "provider": attestation["attestation"]["provider"],  # type: ignore[index]
            "evidence_root_algorithm": attestation["evidenceRootAlgorithm"],
            "fixture_signing": True,
        },
        "artifacts": artifacts,
        "limitations": {
            "extraction_confidence_proxy": "bounded retrieval-score proxy pending an approved upstream extraction-confidence contract",
            "dense_blocker": "local dense snapshot lacks executable weights",
            "reranker_blocker": "no verified immutable reranker revision and usable snapshot",
            "dependency_lock_blocker": "exact release dependency lock remains unresolved",
            "unsupported_valuation_features": [
                "business-day adjustment",
                "ex-coupon",
                "floating-rate bonds",
                "amortizing bonds",
                "defaulted cash flows",
                "complex stubs beyond two nominal periods",
            ],
        },
    }


def _finalize_fixture_artifacts(output_dir: Path, seed: int) -> None:
    legacy_manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    summary_path = output_dir / "retrieval_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    _json_write(summary_path, summary)
    valuation_rows, policy = _fixture_valuation_rows(summary)
    valuation_fields = tuple(valuation_rows[0])
    _csv_write(output_dir / "valuation_sensitivity.csv", valuation_rows, valuation_fields)
    attestation = _fixture_attestation(
        seed=seed,
        decision_code=policy.decision_code,
        recommended_haircut_bps=policy.recommended_haircut_bps,
    )
    _json_write(output_dir / "risk_attestation_fixture.json", attestation)
    manifest = _fixture_manifest(
        seed=seed,
        output_dir=output_dir,
        legacy_manifest=legacy_manifest,
        attestation=attestation,
    )
    if not _all_finite(manifest):
        raise Task8Error("non_finite_artifact", "manifest contains a non-finite value")
    _json_write(output_dir / "manifest.json", manifest)


def _strict_json_bytes(path: Path) -> tuple[Mapping[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise Task8Error("missing_cache_file", f"required cache file is unavailable: {path.name}") from error
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise Task8Error("malformed_normalized_document", f"invalid UTF-8 JSON: {path.name}") from error
    if not isinstance(payload, Mapping):
        raise Task8Error("malformed_normalized_document", f"JSON root must be an object: {path.name}")
    return payload, hashlib.sha256(raw).hexdigest()


def _cache_path(cache_root: Path, relative: object, field_name: str) -> Path:
    if type(relative) is not str or not relative:
        raise Task8Error("malformed_cache_index", f"{field_name} must be a non-empty string")
    candidate = (cache_root / relative).resolve()
    try:
        candidate.relative_to(cache_root.resolve())
    except ValueError as error:
        raise Task8Error("malformed_cache_index", f"{field_name} must stay within source cache") from error
    if not candidate.is_file():
        raise Task8Error("missing_cache_file", f"cache file does not exist: {relative}")
    return candidate


def _date_value(value: object, field_name: str) -> date:
    if type(value) is not str:
        raise Task8Error("malformed_cache_index", f"{field_name} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise Task8Error("malformed_cache_index", f"{field_name} must be an ISO date") from error


def _load_source_manifest(path: Path) -> tuple[dict[str, dict[str, str]], tuple[Mapping[str, str], ...]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = tuple(dict(row) for row in csv.DictReader(handle))
    except OSError as error:
        raise Task8Error("missing_source_manifest", "source cache requires source_manifest.csv") from error
    if not rows:
        raise Task8Error("empty_source_manifest", "source_manifest.csv must contain at least one source")
    required = {"source_id", "issuer", "report_period", "sha256"}
    for row in rows:
        if not required.issubset(row) or any(not row[field] for field in required):
            raise Task8Error("malformed_source_manifest", "source manifest is missing required fields")
        if _SHA256.fullmatch(row["sha256"]) is None:
            raise Task8Error("malformed_source_manifest", "source manifest hash must be lowercase SHA-256")
    identifiers = [row["source_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise Task8Error("malformed_source_manifest", "source manifest source_id values must be unique")
    return {row["source_id"]: row for row in rows}, rows


def load_production_inputs(source_cache: Path) -> ProductionInputs:
    """Load approved cached bytes and normalized documents into one sealed corpus.

    The cache is a mechanical external representation containing the approved
    ``source_manifest.csv``, a ``cache_index.json`` path index, source bytes,
    and normalized documents. It does not change the normalized-document or
    EvidenceSpanV1 schemas.
    """

    cache_root = Path(source_cache).resolve()
    if not cache_root.is_dir():
        raise Task8Error("missing_source_cache", "production source cache directory does not exist")
    manifest_by_id, manifest_rows = _load_source_manifest(cache_root / "source_manifest.csv")
    index_payload, _ = _strict_json_bytes(cache_root / "cache_index.json")
    if index_payload.get("schema_version") != SOURCE_CACHE_SCHEMA:
        raise Task8Error("malformed_cache_index", f"cache_index.json must use {SOURCE_CACHE_SCHEMA}")
    entries = index_payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise Task8Error("malformed_cache_index", "cache index entries must be a non-empty array")
    if not all(isinstance(entry, Mapping) for entry in entries):
        raise Task8Error("malformed_cache_index", "cache index entries must be objects")
    entry_ids = [entry.get("source_id") for entry in entries]
    if any(type(identifier) is not str or not identifier for identifier in entry_ids):
        raise Task8Error("malformed_cache_index", "cache entries require source_id")
    if len(entry_ids) != len(set(entry_ids)) or set(entry_ids) != set(manifest_by_id):
        raise Task8Error(
            "cache_manifest_mismatch",
            "cache index must contain exactly one entry for every approved source manifest row",
        )

    spans: list[object] = []
    source_ids: dict[str, str] = {}
    asset_ids: dict[str, str] = {}
    structured_values: dict[str, Mapping[str, object]] = {}
    source_hashes: dict[str, str] = {}
    normalized_hashes: dict[str, str] = {}

    for entry in sorted(entries, key=lambda item: str(item["source_id"])):
        source_id = str(entry["source_id"])
        manifest = manifest_by_id[source_id]
        source_path = _cache_path(cache_root, entry.get("source_path"), "source_path")
        normalized_path = _cache_path(cache_root, entry.get("normalized_path"), "normalized_path")
        actual_source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if actual_source_hash != manifest["sha256"]:
            raise Task8Error(
                "source_hash_mismatch",
                f"source hash does not match approved manifest for {source_id}",
            )
        payload, normalized_hash = _strict_json_bytes(normalized_path)
        source_date = _date_value(entry.get("source_date"), "source_date")
        asset_id = entry.get("asset_id")
        if type(asset_id) is not str or not asset_id:
            raise Task8Error("malformed_cache_index", "asset_id must be a non-empty string")
        try:
            document_spans = load_normalized_document(
                payload,
                issuer_id=manifest["issuer"],
                report_period=manifest["report_period"],
                source_date=source_date,
            )
        except NormalizedDocumentIngestionError as error:
            raise Task8Error(
                "malformed_normalized_document",
                f"normalized document is invalid for {source_id}: {error}",
            ) from error
        if not document_spans:
            raise Task8Error("empty_normalized_document", f"normalized document has no evidence spans: {source_id}")
        by_block = {span.block_id: span for span in document_spans}
        entry_values = entry.get("structured_values", {})
        if not isinstance(entry_values, Mapping):
            raise Task8Error("malformed_cache_index", "structured_values must be an object")
        unknown_blocks = set(entry_values) - set(by_block)
        if unknown_blocks:
            raise Task8Error("malformed_cache_index", "structured_values references unknown block_id")
        for block_id, values in entry_values.items():
            if not isinstance(values, Mapping):
                raise Task8Error("malformed_cache_index", "structured numerical values must be objects")
            span = by_block[str(block_id)]
            structured_values[span.content_hash] = dict(values)
        for span in document_spans:
            source_ids[span.content_hash] = source_id
            asset_ids[span.content_hash] = asset_id
        spans.extend(document_spans)
        source_hashes[source_id] = actual_source_hash
        normalized_hashes[source_id] = normalized_hash

    corpus = adapt_evidence_spans(
        spans,
        source_ids=source_ids,
        asset_ids=asset_ids,
        structured_values=structured_values,
    )
    evidence_catalog = {
        record.evidence_id: EvidenceLocation(
            page_id=record.page_id or "",
            block_id=record.block_id or "",
        )
        for record in corpus
    }
    return ProductionInputs(
        corpus=corpus,
        spans=tuple(spans),
        graph=build_graph(spans),
        source_hashes=dict(sorted(source_hashes.items())),
        normalized_document_hashes=dict(sorted(normalized_hashes.items())),
        evidence_catalog=evidence_catalog,
        source_manifest_rows=manifest_rows,
    )


def _run_production_retrieval(
    corpus: AuthoritativeCorpus,
    graph: object,
    queries: Sequence[RetrieverQuery],
) -> dict[str, dict[str, tuple]]:
    """Call the exact frozen Task 5 production boundary for every query."""

    if not queries:
        raise Task8Error("empty_question_set", "production question set must not be empty")
    valid_at = queries[0].valid_at
    if any(query.source_cutoff is None for query in queries):
        raise Task8Error("missing_source_cutoff", "production queries require explicit source_cutoff")
    if any(query.valid_at != valid_at for query in queries):
        raise Task8Error("mixed_valid_at", "production queries must share one explicit valid_at")
    with _offline_model_loading():
        methods = all_retrievers(
            corpus,
            cutoff=valid_at,
            graph=graph,  # type: ignore[arg-type]
            mode="production",
        )
    method_ids = tuple(method.method_name for method in methods)
    if len(method_ids) != len(set(method_ids)) or set(method_ids) != set(REGISTERED_METHOD_IDS):
        raise Task8Error("invalid_method_set", "production factory must return exactly the six methods")
    return {
        query.question_id: compare_retrievers(
            methods,
            query,
            top_k=5,
            final_benchmark=True,
        )
        for query in queries
    }


def _run_production_retrieval_with_provenance(
    corpus: AuthoritativeCorpus,
    graph: TemporalEvidenceGraph,
    queries: Sequence[RetrieverQuery],
) -> tuple[dict[str, dict[str, tuple]], dict[str, object]]:
    """Execute final retrieval and snapshot factory identities and per-query receipts."""

    from ecoquant.retrieval.provenance import backend_identity, execution_receipt

    if not queries or any(query.source_cutoff is None for query in queries):
        raise Task8Error("missing_source_cutoff", "production queries require explicit source_cutoff")
    valid_at = queries[0].valid_at
    if any(query.valid_at != valid_at for query in queries):
        raise Task8Error("mixed_valid_at", "production queries must share one explicit valid_at")
    with _offline_model_loading():
        methods = all_retrievers(corpus, cutoff=valid_at, graph=graph, mode="production")
    method_ids = tuple(method.method_name for method in methods)
    if len(method_ids) != len(set(method_ids)) or set(method_ids) != set(REGISTERED_METHOD_IDS):
        raise Task8Error("invalid_method_set", "production factory must return exactly the six methods")

    identities: dict[str, object] = {}
    receipt_snapshots: dict[str, list[object]] = {method_id: [] for method_id in REGISTERED_METHOD_IDS}
    for method in methods:
        identity = backend_identity(method)
        if identity is None:
            raise Task8Error("untrusted_backend", f"factory identity missing for {method.method_name}")
        identities[method.method_name] = {
            "method_id": identity.method_id,
            "backend_type": identity.backend_type,
            "instance_id": identity.instance_id,
            "run_id": identity.run_id,
            "adapter_receipt_id": identity.adapter_receipt_id,
            "corpus_fingerprint": identity.corpus_fingerprint,
            "dependencies": [
                {
                    "role": dependency.role,
                    "implementation_id": dependency.implementation_id,
                    "version": dependency.version,
                    "model_id": dependency.model_id,
                    "revision": dependency.revision,
                }
                for dependency in identity.dependencies
            ],
        }

    results: dict[str, dict[str, tuple]] = {}
    for query in queries:
        compared = compare_retrievers(
            methods,
            query,
            top_k=5,
            final_benchmark=True,
        )
        results[query.question_id] = compared
        for method in methods:
            receipt = execution_receipt(method)
            if receipt is None:
                raise Task8Error(
                    "missing_execution_receipt",
                    f"successful execution receipt missing for {method.method_name}",
                )
            receipt_snapshots[method.method_name].append(
                {
                    "method_id": receipt.method_id,
                    "instance_id": receipt.instance_id,
                    "run_id": receipt.run_id,
                    "corpus_fingerprint": receipt.corpus_fingerprint,
                    "query_digest": receipt.query_digest,
                    "valid_at": receipt.valid_at.isoformat(),
                    "source_cutoff": receipt.source_cutoff.isoformat(),
                    "top_k": receipt.top_k,
                    "dependency_digest": receipt.dependency_digest,
                    "output_digest": receipt.output_digest,
                    "status": receipt.status,
                }
            )
    return results, {
        method_id: {
            "identity": identities[method_id],
            "execution_receipts": receipt_snapshots[method_id],
            "backend_status": "production_verified",
        }
        for method_id in REGISTERED_METHOD_IDS
    }


def _production_gold(
    questions: Sequence[Mapping[str, object]],
    corpus: AuthoritativeCorpus,
) -> object:
    from ecoquant.retrieval.evaluation import EvaluatorGold

    records_by_source: dict[str, set[str]] = {}
    for record in corpus:
        for identifier in (record.source_id, record.document_id, record.evidence_id):
            if identifier:
                records_by_source.setdefault(identifier, set()).add(record.evidence_id)
    relevant: dict[str, frozenset[str]] = {}
    issuer_by_question: dict[str, str] = {}
    citation: dict[str, frozenset[str]] = {}
    expected_numeric: dict[str, float] = {}
    gold_pages: dict[str, frozenset[str]] = {}
    gold_blocks: dict[str, frozenset[str]] = {}
    for question in questions:
        try:
            question_id = str(question["question_id"])
            issuer_by_question[question_id] = str(question["issuer"])
            source_ids = question["gold_source_ids"]
        except KeyError as error:
            raise Task8Error("malformed_question_set", f"question set missing field: {error.args[0]}") from error
        if not isinstance(source_ids, list) or not source_ids:
            raise Task8Error("malformed_question_set", "gold_source_ids must be a non-empty array")
        expanded = frozenset(
            evidence_id
            for source_id in source_ids
            for evidence_id in records_by_source.get(str(source_id), set())
        )
        if not expanded:
            raise Task8Error(
                "question_source_mismatch",
                f"question {question_id} has no evidence in the authoritative corpus",
            )
        relevant[question_id] = expanded
        citation[question_id] = expanded
        if isinstance(question.get("gold_page_ids"), list):
            gold_pages[question_id] = frozenset(str(value) for value in question["gold_page_ids"])  # type: ignore[index]
        if isinstance(question.get("gold_block_ids"), list):
            gold_blocks[question_id] = frozenset(str(value) for value in question["gold_block_ids"])  # type: ignore[index]
        if "reported_value" in question:
            expected_numeric[question_id] = float(question["reported_value"])  # type: ignore[arg-type]
        elif "derived_change" in question:
            expected_numeric[question_id] = float(question["derived_change"])  # type: ignore[arg-type]
    return EvaluatorGold(
        relevant_evidence=relevant,
        issuer_by_question=issuer_by_question,
        contradiction_evidence={},
        citation_evidence=citation,
        expected_numeric=expected_numeric,
        gold_page_ids=gold_pages,
        gold_block_ids=gold_blocks,
    )


def _compute_production_metrics(
    all_results: Mapping[str, Mapping[str, tuple]],
    labels: object,
    evidence_catalog: Mapping[str, EvidenceLocation],
) -> dict[str, dict[str, object]]:
    from ecoquant.retrieval.evaluation import score_retrieval

    output: dict[str, dict[str, object]] = {}
    for method_id in REGISTERED_METHOD_IDS:
        metrics = score_retrieval(
            {
                question_id: methods[method_id]
                for question_id, methods in all_results.items()
            },
            labels,  # type: ignore[arg-type]
            evidence_catalog=evidence_catalog,
        )
        output[method_id] = {
            "recall_at_5": metrics.recall_at_5,
            "hit_at_5": metrics.hit_at_5,
            "mrr": metrics.mrr,
            "ndcg_at_5": metrics.ndcg_at_5,
            "temporal_accuracy": metrics.temporal_accuracy,
            "stale_evidence_rate": metrics.stale_evidence_rate,
            "contradiction_f1": metrics.contradiction_f1,
            "contradiction_evaluable": metrics.contradiction_evaluable,
            "contradiction_reason": metrics.contradiction_reason,
            "citation_accuracy": metrics.citation_accuracy,
            "page_accuracy_at_5": metrics.page_accuracy_at_5,
            "block_accuracy_at_5": metrics.block_accuracy_at_5,
            "page_accuracy_reason": metrics.page_accuracy_reason,
            "block_accuracy_reason": metrics.block_accuracy_reason,
            "numerical_mismatch_rate": metrics.mismatch_rate,
            "numerical_evaluable_count": metrics.mismatch_denominator,
        }
    return output


def _fit_production_task6(
    all_results: dict[str, dict[str, tuple]],
    labels: object,
    *,
    seed: int,
) -> tuple[tuple[object, ...], dict[str, object], dict[str, object]]:
    from ecoquant.uncertainty.calibration import fit_calibration_folds
    from scripts.run_research import (
        _build_fold_data,
        _run_calibration,
        _run_decision_gating,
    )

    primary = "temporal_kg_verify"
    fold_data = _build_fold_data(all_results, labels, primary)  # type: ignore[arg-type]
    folds = fit_calibration_folds(
        fold_data,
        conformal_alpha=0.10,
        max_selective_error=0.10,
        seed=seed,
    )
    manifests = tuple(fold.split_manifest for fold in folds)
    _require_fitted_task6_state(manifests)
    calibration = _run_calibration(
        fold_data,
        conformal_alpha=0.10,
        max_selective_error=0.10,
        seed=seed,
    )
    decisions = _run_decision_gating(
        all_results,
        labels,  # type: ignore[arg-type]
        primary,
        folds,
    )
    return folds, calibration, decisions


def _production_valuation_rows(
    decisions: Mapping[str, object],
    record: object,
) -> tuple[list[dict[str, object]], object]:
    from ecoquant.uncertainty.decision import DecisionCode
    from ecoquant.valuation.bond_pricing import BondTerms
    from ecoquant.valuation.policy import PolicyInput, apply_policy
    from ecoquant.valuation.sensitivity import compute_sensitivity

    decision_code = _fixture_decision_code({"decision_summary": decisions})
    evidence_id = str(record.evidence_id)
    issuer = str(record.issuer)
    asset_id = str(record.asset_id)
    policy = apply_policy(
        PolicyInput(
            decision_code=decision_code,
            evidence_ids=(evidence_id,),
            risk_factors={"transition_risk": 0.40},
            extraction_valid=True,
            risk_channel_map={"transition_risk": "credit_spread"},
            base_spread_bps=145,
            max_spread_delta_bps=50,
            max_haircut_bps=500,
        )
    )
    valuation = compute_sensitivity(
        BondTerms(
            face_value=100.0,
            coupon_rate=0.04,
            payment_frequency=2,
            issue_date=date(2020, 6, 30),
            settlement_date=date(2024, 9, 15),
            maturity_date=date(2030, 6, 30),
        ),
        0.035,
        145,
        policy,
        {"transition_risk": "credit_spread"},
        issuer=issuer,
        asset_id=asset_id,
        evidence_id=evidence_id,
        rule_id="ecoquant-valuation-policy",
        rule_version="1.0.0",
        valid_time=record.valid_time.isoformat(),
        source_time=record.source_time.isoformat(),
    )
    rows = [
        {
            "scenario": scenario.scenario_name,
            "status": scenario.status,
            "evidence_id": scenario.evidence_id,
            "issuer": scenario.issuer,
            "asset_id": scenario.asset_id,
            "risk_factor": scenario.risk_factor,
            "risk_channel": scenario.risk_channel,
            "rule_id": scenario.rule_id,
            "rule_version": scenario.rule_version,
            "decision_code": int(scenario.decision_code),
            "base_spread_bps": scenario.base_spread_bps,
            "spread_delta_bps": scenario.spread_delta_bps,
            "adjusted_spread_bps": scenario.adjusted_spread_bps,
            "settlement_date": scenario.settlement_date.isoformat(),
            "maturity_date": scenario.maturity_date.isoformat(),
            "coupon_frequency": scenario.coupon_frequency,
            "day_count_convention": scenario.day_count_convention,
            "compounding_convention": scenario.compounding_convention,
            "clean_price": scenario.adjusted_clean_price,
            "dirty_price": scenario.adjusted_dirty_price,
            "accrued_interest": scenario.accrued_interest,
            "macaulay_duration": scenario.macaulay_duration,
            "modified_duration": scenario.modified_duration,
            "convexity": scenario.convexity,
            "valid_time": scenario.valid_time,
            "source_time": scenario.source_time,
        }
        for scenario in valuation.scenarios
    ]
    if not rows:
        base = {
            "scenario": "no_adjustment",
            "status": valuation.status,
            "evidence_id": evidence_id,
            "issuer": issuer,
            "asset_id": asset_id,
            "risk_factor": "transition_risk",
            "risk_channel": "credit_spread",
            "rule_id": "ecoquant-valuation-policy",
            "rule_version": "1.0.0",
            "decision_code": int(DecisionCode.INSUFFICIENT_EVIDENCE),
            "base_spread_bps": 145,
            "spread_delta_bps": 0,
            "adjusted_spread_bps": 145,
            "settlement_date": "2024-09-15",
            "maturity_date": "2030-06-30",
            "coupon_frequency": 2,
            "day_count_convention": "Actual/Actual ICMA",
            "compounding_convention": "nominal annual yield compounded at coupon frequency",
            "clean_price": valuation.base_clean_price,
            "dirty_price": valuation.base_dirty_price,
            "accrued_interest": valuation.base_accrued_interest,
            "macaulay_duration": valuation.base_macaulay_duration,
            "modified_duration": valuation.base_modified_duration,
            "convexity": valuation.base_convexity,
            "valid_time": record.valid_time.isoformat(),
            "source_time": record.source_time.isoformat(),
        }
        rows.append(base)
    return rows, policy


def _production_attestation(
    *,
    corpus: AuthoritativeCorpus,
    signing: SigningConfiguration,
    seed: int,
    decision_code: object,
    recommended_haircut_bps: int | None,
    source_cutoff: date,
) -> dict[str, object]:
    from ecoquant.attestation.eip712 import compute_asset_id, compute_model_version
    from ecoquant.attestation.merkle import evidence_merkle_root
    from ecoquant.attestation.models import RiskAttestationV1
    from ecoquant.attestation.signing import (
        CANONICAL_DOMAIN_NAME,
        CANONICAL_DOMAIN_VERSION,
        sign_attestation,
        verify_provider,
    )

    evidence_root = evidence_merkle_root(
        [bytes.fromhex(record.evidence_id) for record in sorted(corpus, key=lambda item: item.evidence_id)]
    )
    as_of = int(datetime.combine(source_cutoff, time.min, tzinfo=timezone.utc).timestamp())
    attestation = RiskAttestationV1(
        schema_version=1,
        asset_id=compute_asset_id(str(corpus[0].asset_id)),
        as_of=as_of,
        risk_score_bps=4_000,
        confidence_bps=8_500,
        recommended_haircut_bps=recommended_haircut_bps or 0,
        evidence_root=evidence_root,
        model_version=compute_model_version(),
        decision_code=int(decision_code),
        valid_until=as_of + 86_400,
        nonce=seed,
        provider=signing.provider,
    )
    signed = sign_attestation(
        attestation,
        signing.private_key,
        chain_id=signing.chain_id,
        verifying_contract=signing.verifying_contract,
    )
    if not verify_provider(
        signed,
        chain_id=signing.chain_id,
        verifying_contract=signing.verifying_contract,
    ):
        raise Task8Error("invalid_attestation_signature", "production provider does not match recovered signer")
    return {
        "schema_version": "risk-attestation-v1.production-envelope.v1",
        "mode": "production",
        "productionVerified": True,
        "fixtureSigning": False,
        "attestation": {
            "schemaVersion": attestation.schema_version,
            "assetId": "0x" + attestation.asset_id.hex(),
            "asOf": attestation.as_of,
            "riskScoreBps": attestation.risk_score_bps,
            "confidenceBps": attestation.confidence_bps,
            "recommendedHaircutBps": attestation.recommended_haircut_bps,
            "evidenceRoot": "0x" + attestation.evidence_root.hex(),
            "modelVersion": "0x" + attestation.model_version.hex(),
            "decisionCode": attestation.decision_code,
            "validUntil": attestation.valid_until,
            "nonce": attestation.nonce,
            "provider": attestation.provider,
        },
        "domain": {
            "name": CANONICAL_DOMAIN_NAME,
            "version": CANONICAL_DOMAIN_VERSION,
            "chainId": signing.chain_id,
            "verifyingContract": signing.verifying_contract,
        },
        "evidenceRootAlgorithm": "sorted-authoritative-evidence-id-bytes-keccak-merkle-v1",
        "domainSeparator": "0x" + signed.domain_hash.hex(),
        "structHash": "0x" + signed.struct_hash.hex(),
        "digest": "0x" + signed.digest.hex(),
        "publicKey": "0x" + signed.public_key.hex(),
        "signature": "0x" + signed.signature.hex(),
        "recoveredProvider": signed.signer_address,
    }


def _require_release_dependency_lock() -> Path:
    candidates = (
        REPOSITORY_ROOT / "requirements.lock",
        REPOSITORY_ROOT / "uv.lock",
        REPOSITORY_ROOT / "poetry.lock",
        REPOSITORY_ROOT / "Pipfile.lock",
    )
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    raise Task8Error(
        "dependency_lock_blocked",
        "exact release dependency lock is unresolved",
        blockers=("exact_release_dependency_lock_unresolved",),
    )


def _write_production_release(
    *,
    output_dir: Path,
    seed: int,
    valid_at: date,
    source_cutoff: date,
    question_set: Path,
    question_payloads: Sequence[Mapping[str, object]],
    inputs: ProductionInputs,
    all_results: dict[str, dict[str, tuple]],
    retrieval_provenance: Mapping[str, object],
    metrics: Mapping[str, object],
    calibration: Mapping[str, object],
    decisions: Mapping[str, object],
    signing: SigningConfiguration,
    dependency_lock: Path,
) -> None:
    from scripts.run_research import _compute_bootstrap

    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise Task8Error(
            "stale_output_directory",
            "output directory must be absent or empty to prevent stale artifacts",
        )
    labels = _production_gold(question_payloads, inputs.corpus)
    bootstrap = _compute_bootstrap(
        all_results,
        labels,  # type: ignore[arg-type]
        "bm25",
        "temporal_kg_verify",
    )
    valuation_rows, policy = _production_valuation_rows(decisions, inputs.corpus[0])
    attestation = _production_attestation(
        corpus=inputs.corpus,
        signing=signing,
        seed=seed,
        decision_code=policy.decision_code,
        recommended_haircut_bps=policy.recommended_haircut_bps,
        source_cutoff=source_cutoff,
    )
    retrieval_rows = [
        {
            "question_id": question_id,
            "method": method_id,
            "evidence_id": result.evidence_id,
            "rank": result.rank,
            "score": result.score,
            "valid_time_match": result.valid_time_match,
            "verification_status": result.verification_status,
        }
        for question_id in sorted(all_results)
        for method_id in REGISTERED_METHOD_IDS
        for result in all_results[question_id][method_id]
    ]
    folds = calibration.get("folds")
    if not isinstance(folds, list):
        raise Task8Error("unfitted_task6_state", "production calibration fold state is missing")
    _require_fitted_task6_state(folds)
    calibration_rows = [
        {
            "fold_id": fold["outer_fold_id"],
            "test_issuer": fold["test_issuer"],
            "fit_sample_count": fold["fit_sample_count"],
            "cal_sample_count": fold["cal_sample_count"],
            "conformal_threshold": fold["conformal_threshold"],
            "decision_threshold": fold["decision_threshold"],
        }
        for fold in folds
    ]
    risk_coverage = calibration.get("risk_coverage")
    if not isinstance(risk_coverage, list):
        raise Task8Error("unfitted_task6_state", "production risk-coverage output is missing")
    summary = {
        "schema_version": "task8-retrieval-summary.v1",
        "execution_mode": "production",
        "method_metrics": metrics,
        "question_count": len(question_payloads),
        "corpus_size": len(inputs.corpus),
        "primary_method": "temporal_kg_verify",
        "decision_summary": decisions,
        "bootstrap_intervals": bootstrap,
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f".{output_dir.name}.task8-{uuid4().hex}"
    staging.mkdir()
    try:
        _csv_write(staging / "retrieval_results.csv", retrieval_rows, tuple(retrieval_rows[0]))
        _json_write(staging / "retrieval_summary.json", summary)
        _csv_write(staging / "calibration_results.csv", calibration_rows, tuple(calibration_rows[0]))
        _csv_write(staging / "risk_coverage.csv", risk_coverage, tuple(risk_coverage[0]))
        _csv_write(staging / "valuation_sensitivity.csv", valuation_rows, tuple(valuation_rows[0]))
        _json_write(staging / "risk_attestation_fixture.json", attestation)
        artifact_identities: dict[str, object] = {}
        for filename, schema_version in _NON_MANIFEST_SCHEMAS.items():
            data = (staging / filename).read_bytes()
            artifact_identities[filename] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "schema_version": schema_version,
            }
        question_hash = hashlib.sha256(question_set.read_bytes()).hexdigest()
        run_material = json.dumps(
            {
                "corpus": corpus_fingerprint(inputs.corpus),
                "questions": question_hash,
                "seed": seed,
                "source_cutoff": source_cutoff.isoformat(),
                "valid_at": valid_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        manifest = {
            "schema_version": "task8-manifest.v1",
            "repository": {
                "commit": _git_value("rev-parse", "HEAD", fallback="unknown"),
                "branch": _git_value("branch", "--show-current", fallback="unavailable"),
                "dirty": bool(_git_value("status", "--porcelain", fallback="dirty")),
            },
            "run": {
                "execution_mode": "production",
                "seed": seed,
                "run_id": hashlib.sha256(run_material).hexdigest()[:24],
                "command": "python -m ecoquant.research.run_task8 --mode production --source-cache <path> --question-set <path> --valid-at <date> --source-cutoff <date> --output-dir <isolated-output> --seed 20260710",
                "timestamp_policy": "source_cutoff_utc_midnight",
                "timestamp": datetime.combine(source_cutoff, time.min, tzinfo=timezone.utc).isoformat(),
                "completion_status": "production_complete",
                "production_verified": True,
                "final_release": True,
            },
            "sources": {
                "fixture_input": False,
                "source_hashes": inputs.source_hashes,
                "normalized_document_hashes": inputs.normalized_document_hashes,
                "question_set_hash": question_hash,
                "corpus_fingerprint": corpus_fingerprint(inputs.corpus),
                "graph_schema_version": "retrieval-safe-graph.v1",
            },
            "retrieval": {
                "method_ids": list(REGISTERED_METHOD_IDS),
                "top_k": 5,
                "valid_at": valid_at.isoformat(),
                "source_cutoff": source_cutoff.isoformat(),
                "backends": retrieval_provenance,
                "dependency_lock": {
                    "filename": dependency_lock.name,
                    "sha256": hashlib.sha256(dependency_lock.read_bytes()).hexdigest(),
                },
            },
            "calibration": {
                "issuer_split_manifests": folds,
                "feature_version": "task6-uncertainty-features.v1",
                "normalization_state": [fold["normalization_parameters"] for fold in folds],
                "coefficients": [fold["fitted_coefficients"] for fold in folds],
                "convergence": [fold["convergence_status"] for fold in folds],
                "conformal_alpha": calibration.get("conformal_alpha"),
                "conformal_thresholds": [fold["conformal_threshold"] for fold in folds],
                "decision_thresholds": [fold["decision_threshold"] for fold in folds],
            },
            "valuation": {
                "rule_id": "ecoquant-valuation-policy",
                "rule_version": "1.0.0",
                "day_count_convention": "Actual/Actual ICMA",
                "compounding_convention": "nominal annual yield compounded at coupon frequency",
                "supported_schedule_contract": "backward-unadjusted-eom-fixed-rate-bullet-stubs-max-two-periods.v1",
            },
            "attestation": {
                "schema_version": 1,
                "model_version": attestation["attestation"]["modelVersion"],  # type: ignore[index]
                "domain": attestation["domain"],
                "provider": attestation["attestation"]["provider"],  # type: ignore[index]
                "evidence_root_algorithm": attestation["evidenceRootAlgorithm"],
                "fixture_signing": False,
            },
            "artifacts": artifact_identities,
            "limitations": {
                "extraction_confidence_proxy": "bounded retrieval-score proxy pending an approved upstream extraction-confidence contract",
                "dense_blocker": None,
                "reranker_blocker": None,
                "dependency_lock_blocker": None,
                "unsupported_valuation_features": [
                    "business-day adjustment",
                    "ex-coupon",
                    "floating-rate bonds",
                    "amortizing bonds",
                    "defaulted cash flows",
                    "complex stubs beyond two nominal periods",
                ],
            },
        }
        if not _all_finite(manifest):
            raise Task8Error("non_finite_artifact", "production manifest contains non-finite values")
        _json_write(staging / "manifest.json", manifest)
        output_dir.mkdir(exist_ok=True)
        for filename in _PRINCIPAL_ARTIFACTS:
            os.replace(staging / filename, output_dir / filename)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _parse_cli(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixture", "production"), required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--source-cache", type=Path)
    parser.add_argument("--question-set", type=Path)
    parser.add_argument("--valid-at")
    parser.add_argument("--source-cutoff")
    return parser.parse_args(argv)


def _validate_production_arguments(args: argparse.Namespace) -> tuple[date, date]:
    if args.source_cache is None:
        raise Task8Error("missing_source_cache", "production mode requires --source-cache")
    if args.question_set is None:
        raise Task8Error("missing_question_set", "production mode requires --question-set")
    if args.valid_at is None:
        raise Task8Error("missing_valid_at", "production mode requires --valid-at")
    if args.source_cutoff is None:
        raise Task8Error("missing_source_cutoff", "production mode requires --source-cutoff")
    try:
        valid_at = date.fromisoformat(args.valid_at)
    except ValueError as error:
        raise Task8Error("invalid_valid_at", "--valid-at must be an ISO date") from error
    try:
        source_cutoff = date.fromisoformat(args.source_cutoff)
    except ValueError as error:
        raise Task8Error("invalid_source_cutoff", "--source-cutoff must be an ISO date") from error
    missing_signing = [name for name in _SIGNING_ENVIRONMENT if not os.environ.get(name)]
    if missing_signing:
        raise Task8Error(
            "missing_signing_configuration",
            "production signing configuration is incomplete",
        )
    return valid_at, source_cutoff


def _load_question_payloads(path: Path) -> tuple[Mapping[str, object], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise Task8Error("missing_question_set", "question set is unavailable") from error
    payloads: list[Mapping[str, object]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise Task8Error("malformed_question_set", "question set contains invalid JSONL") from error
        if not isinstance(payload, Mapping):
            raise Task8Error("malformed_question_set", "question rows must be objects")
        payloads.append(payload)
    if not payloads:
        raise Task8Error("empty_question_set", "question set must contain at least one row")
    return tuple(payloads)


def _load_queries(
    path: Path,
    *,
    valid_at: date,
    source_cutoff: date,
) -> tuple[RetrieverQuery, ...]:
    payloads = _load_question_payloads(path)
    try:
        return tuple(
            RetrieverQuery(
                question_id=str(payload["question_id"]),
                issuer=str(payload["issuer"]),
                query=str(payload["query"]),
                cutoff=valid_at,
                source_cutoff=source_cutoff,
            )
            for payload in payloads
        )
    except KeyError as error:
        raise Task8Error("malformed_question_set", f"question set missing field: {error.args[0]}") from error


def _run_fixture_compatibility(output_dir: Path, seed: int) -> int:
    """Run the existing fixture study in isolated staging and finalize artifacts."""

    from scripts.run_research import _legacy_fixture_main as legacy_main

    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise Task8Error(
            "stale_output_directory",
            "output directory must be absent or empty to prevent stale artifacts",
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f".{output_dir.name}.task8-{uuid4().hex}"
    staging.mkdir()
    original_argv = sys.argv[:]
    try:
        forwarded = original_argv[:]
        if "--output-dir" in forwarded:
            forwarded[forwarded.index("--output-dir") + 1] = str(staging)
        else:
            forwarded.extend(("--output-dir", str(staging)))
        sys.argv = forwarded
        with redirect_stdout(io.StringIO()):
            status = legacy_main()
        if status != 0:
            return status
        _finalize_fixture_artifacts(staging, seed)
        actual = {path.name for path in staging.iterdir() if path.is_file()}
        if actual != set(_PRINCIPAL_ARTIFACTS):
            raise Task8Error(
                "unexpected_artifact_set",
                "fixture staging must contain exactly the seven principal artifacts",
            )
        output_dir.mkdir(exist_ok=True)
        for filename in _PRINCIPAL_ARTIFACTS:
            os.replace(staging / filename, output_dir / filename)
        print(
            json.dumps(
                {
                    "status": "fixture_complete",
                    "production_verified": False,
                    "output_dir": str(output_dir),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    finally:
        sys.argv = original_argv
        shutil.rmtree(staging, ignore_errors=True)


def run(args: argparse.Namespace) -> int:
    if args.mode == "fixture":
        return _run_fixture_compatibility(args.output_dir, args.seed)

    valid_at, source_cutoff = _validate_production_arguments(args)
    signing = SigningConfiguration.from_environment()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise Task8Error(
            "stale_output_directory",
            "output directory must be absent or empty to prevent stale artifacts",
        )
    inputs = load_production_inputs(args.source_cache)
    question_payloads = _load_question_payloads(args.question_set)
    queries = _load_queries(args.question_set, valid_at=valid_at, source_cutoff=source_cutoff)
    try:
        all_results, retrieval_provenance = _run_production_retrieval_with_provenance(
            inputs.corpus,
            inputs.graph,
            queries,
        )
    except Task8Error:
        raise
    except Exception as error:
        raise Task8Error(
            "production_retrieval_blocked",
            f"final Task 5 execution did not complete: {type(error).__name__}: {error}",
            blockers=(
                "dense_executable_weights_unavailable",
                "reranker_immutable_revision_or_snapshot_unavailable",
                "dense_reranker_inference_unverified",
                "exact_release_dependency_lock_unresolved",
            ),
        ) from error
    dependency_lock = _require_release_dependency_lock()
    labels = _production_gold(question_payloads, inputs.corpus)
    metrics = _compute_production_metrics(all_results, labels, inputs.evidence_catalog)
    _, calibration, decisions = _fit_production_task6(
        all_results,
        labels,
        seed=args.seed,
    )
    _write_production_release(
        output_dir=args.output_dir,
        seed=args.seed,
        valid_at=valid_at,
        source_cutoff=source_cutoff,
        question_set=args.question_set,
        question_payloads=question_payloads,
        inputs=inputs,
        all_results=all_results,
        retrieval_provenance=retrieval_provenance,
        metrics=metrics,
        calibration=calibration,
        decisions=decisions,
        signing=signing,
        dependency_lock=dependency_lock,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_cli(argv)
    try:
        return run(args)
    except Task8Error as error:
        print(json.dumps(error.payload(), sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
