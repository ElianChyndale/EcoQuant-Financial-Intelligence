"""Contract tests for the SOL-4B Task 8 release pipeline."""

from __future__ import annotations

import json
import csv
import hashlib
import math
import os
import subprocess
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from ecoquant.research import run_task8
from ecoquant.attestation.models import RiskAttestationV1
from ecoquant.attestation.signing import SignedAttestation, verify_provider
from ecoquant.retrieval.base import REGISTERED_METHOD_IDS, RetrieverQuery, corpus_fingerprint

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PRINCIPAL_ARTIFACTS = {
    "retrieval_results.csv",
    "retrieval_summary.json",
    "calibration_results.csv",
    "risk_coverage.csv",
    "valuation_sensitivity.csv",
    "risk_attestation_fixture.json",
    "manifest.json",
}


@pytest.fixture(scope="module")
def fixture_release(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("task8-fixture") / "release"
    completed = _run_cli(
        "--mode",
        "fixture",
        "--output-dir",
        str(output_dir),
        "--seed",
        "20260710",
    )
    assert completed.returncode == 0, completed.stderr
    return output_dir


def _run_cli(
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ecoquant.research.run_task8", *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def _source_cache(
    root: Path,
    *,
    source_bytes: bytes = b"approved report bytes",
    normalized_text: str = "Synthetic allocation detail for renewable-energy projects.",
) -> Path:
    cache = root / hashlib.sha256(source_bytes + normalized_text.encode()).hexdigest()[:12]
    (cache / "raw").mkdir(parents=True)
    (cache / "normalized").mkdir()
    raw_path = cache / "raw" / "issuer-2024.pdf"
    raw_path.write_bytes(source_bytes)

    normalized = json.loads(
        (REPOSITORY_ROOT / "tests" / "fixtures" / "normalized_document_v1.json").read_text(
            encoding="utf-8"
        )
    )
    normalized["document_id"] = "issuer-2024-document"
    normalized["pages"][0]["blocks"][0]["content"]["text"] = normalized_text
    normalized_path = cache / "normalized" / "issuer-2024.json"
    normalized_path.write_text(
        json.dumps(normalized, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    with (cache / "source_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "source_id",
                "issuer",
                "title",
                "report_period",
                "official_url",
                "access_date",
                "sha256",
                "media_type",
                "redistribution_status",
                "cache_policy",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_id": "issuer-2024",
                "issuer": "issuer-northstar",
                "title": "Issuer report 2024",
                "report_period": "2024",
                "official_url": "https://example.invalid/issuer-2024.pdf",
                "access_date": "2026-07-10",
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "media_type": "application/pdf",
                "redistribution_status": "test-fixture",
                "cache_policy": "isolated-test-cache",
            }
        )
    (cache / "cache_index.json").write_text(
        json.dumps(
            {
                "schema_version": "ecoquant-source-cache.v1",
                "entries": [
                    {
                        "source_id": "issuer-2024",
                        "source_path": "raw/issuer-2024.pdf",
                        "normalized_path": "normalized/issuer-2024.json",
                        "source_date": "2025-03-01",
                        "asset_id": "asset-northstar",
                        "structured_values": {
                            "block-1": {"allocation_amount": "125000000.00"}
                        },
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return cache


def test_fixture_output_cannot_claim_production(tmp_path: Path) -> None:
    output_dir = tmp_path / "fixture-release"

    completed = _run_cli(
        "--mode",
        "fixture",
        "--output-dir",
        str(output_dir),
        "--seed",
        "20260710",
    )

    assert completed.returncode == 0, completed.stderr
    assert {path.name for path in output_dir.iterdir()} == PRINCIPAL_ARTIFACTS
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    attestation = json.loads(
        (output_dir / "risk_attestation_fixture.json").read_text(encoding="utf-8")
    )
    assert manifest["run"]["execution_mode"] == "fixture"
    assert manifest["run"]["completion_status"] == "fixture_complete"
    assert manifest["run"]["production_verified"] is False
    assert manifest["run"]["final_release"] is False
    assert attestation["mode"] == "fixture"
    assert attestation["productionVerified"] is False
    completion = json.loads(completed.stdout.strip().splitlines()[-1])
    assert completion["status"] == "fixture_complete"
    assert completion["production_verified"] is False


def test_production_without_source_cache_fails_without_fixture_fallback(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "production-release"

    completed = _run_cli(
        "--mode",
        "production",
        "--output-dir",
        str(output_dir),
        "--seed",
        "20260710",
    )

    assert completed.returncode != 0
    error = json.loads(completed.stderr.strip().splitlines()[-1])
    assert error["status"] == "blocked"
    assert error["code"] == "missing_source_cache"
    assert "fixture" not in completed.stdout.casefold()
    assert not output_dir.exists()


def test_legacy_script_entrypoint_enforces_same_production_gate(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_research.py",
            "--mode",
            "production",
            "--output-dir",
            str(tmp_path / "release"),
            "--seed",
            "20260710",
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    error = json.loads(completed.stderr.strip().splitlines()[-1])
    assert error["code"] == "missing_source_cache"


@pytest.mark.parametrize(
    ("omitted_option", "expected_code"),
    [
        ("--valid-at", "missing_valid_at"),
        ("--source-cutoff", "missing_source_cutoff"),
    ],
)
def test_production_requires_explicit_temporal_cutoffs(
    tmp_path: Path,
    omitted_option: str,
    expected_code: str,
) -> None:
    cache = _source_cache(tmp_path)
    output_dir = tmp_path / "production-release"
    arguments = [
        "--mode",
        "production",
        "--source-cache",
        str(cache),
        "--question-set",
        str(REPOSITORY_ROOT / "research" / "questions" / "questions.jsonl"),
        "--valid-at",
        "2025-12-31",
        "--source-cutoff",
        "2025-06-30",
        "--output-dir",
        str(output_dir),
        "--seed",
        "20260710",
    ]
    index = arguments.index(omitted_option)
    del arguments[index : index + 2]

    completed = _run_cli(*arguments)

    assert completed.returncode != 0
    error = json.loads(completed.stderr.strip().splitlines()[-1])
    assert error["code"] == expected_code
    assert not output_dir.exists()


def test_production_requires_external_signing_configuration(tmp_path: Path) -> None:
    cache = _source_cache(tmp_path)
    environment = os.environ.copy()
    for name in (
        "ECOQUANT_SIGNING_KEY_HEX",
        "ECOQUANT_SIGNING_PROVIDER",
        "ECOQUANT_SIGNING_CHAIN_ID",
        "ECOQUANT_SIGNING_CONTRACT",
    ):
        environment.pop(name, None)

    completed = _run_cli(
        "--mode",
        "production",
        "--source-cache",
        str(cache),
        "--question-set",
        str(REPOSITORY_ROOT / "research" / "questions" / "questions.jsonl"),
        "--valid-at",
        "2025-12-31",
        "--source-cutoff",
        "2025-06-30",
        "--output-dir",
        str(tmp_path / "production-release"),
        "--seed",
        "20260710",
        environment=environment,
    )

    assert completed.returncode != 0
    error = json.loads(completed.stderr.strip().splitlines()[-1])
    assert error["code"] == "missing_signing_configuration"
    assert "private" not in completed.stdout.casefold()


def test_identical_production_adaptation_is_deterministic_and_authoritative(
    tmp_path: Path,
) -> None:
    cache = _source_cache(tmp_path)

    first = run_task8.load_production_inputs(cache)
    second = run_task8.load_production_inputs(cache)

    assert first.source_hashes == second.source_hashes
    assert first.normalized_document_hashes == second.normalized_document_hashes
    assert corpus_fingerprint(first.corpus) == corpus_fingerprint(second.corpus)
    assert first.corpus[0].document_id == "issuer-2024-document"
    assert first.corpus[0].issuer == "issuer-northstar"
    assert first.corpus[0].asset_id == "asset-northstar"
    assert first.corpus[0].source_time == date(2025, 3, 1)
    assert first.corpus[0].valid_time == date(2024, 12, 31)
    assert first.corpus[0].page_id == "1"
    assert first.corpus[0].block_id == "block-1"
    assert first.corpus[0].structured_values == (("allocation_amount", "125000000.00"),)
    assert first.evidence_catalog[first.corpus[0].evidence_id].block_id == "block-1"


def test_changed_source_and_normalized_bytes_change_recorded_hashes(tmp_path: Path) -> None:
    baseline = run_task8.load_production_inputs(_source_cache(tmp_path / "one"))
    source_changed = run_task8.load_production_inputs(
        _source_cache(tmp_path / "two", source_bytes=b"different approved report bytes")
    )
    normalized_changed = run_task8.load_production_inputs(
        _source_cache(tmp_path / "three", normalized_text="Changed normalized evidence text.")
    )

    assert baseline.source_hashes != source_changed.source_hashes
    assert baseline.normalized_document_hashes == source_changed.normalized_document_hashes
    assert baseline.normalized_document_hashes != normalized_changed.normalized_document_hashes
    assert corpus_fingerprint(baseline.corpus) != corpus_fingerprint(normalized_changed.corpus)


def test_malformed_or_hash_mismatched_production_source_fails(tmp_path: Path) -> None:
    cache = _source_cache(tmp_path)
    (cache / "raw" / "issuer-2024.pdf").write_bytes(b"tampered")

    with pytest.raises(run_task8.Task8Error, match="source hash") as error:
        run_task8.load_production_inputs(cache)

    assert error.value.code == "source_hash_mismatch"


def test_malformed_normalized_document_fails_with_machine_readable_error(
    tmp_path: Path,
) -> None:
    cache = _source_cache(tmp_path)
    normalized_path = cache / "normalized" / "issuer-2024.json"
    payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    payload.pop("document_id")
    normalized_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(run_task8.Task8Error, match="normalized document") as error:
        run_task8.load_production_inputs(cache)

    assert error.value.code == "malformed_normalized_document"


def test_production_calls_exact_final_task5_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    corpus = run_task8.load_production_inputs(_source_cache(tmp_path)).corpus
    graph = object()
    methods = tuple(type("Method", (), {"method_name": method_id})() for method_id in REGISTERED_METHOD_IDS)
    observed: dict[str, object] = {}

    def fake_all_retrievers(*args: object, **kwargs: object) -> tuple[object, ...]:
        observed["factory_args"] = args
        observed["factory_kwargs"] = kwargs
        return methods

    def fake_compare(*args: object, **kwargs: object) -> dict[str, tuple]:
        observed["compare_args"] = args
        observed["compare_kwargs"] = kwargs
        return {method_id: () for method_id in REGISTERED_METHOD_IDS}

    monkeypatch.setattr(run_task8, "all_retrievers", fake_all_retrievers)
    monkeypatch.setattr(run_task8, "compare_retrievers", fake_compare)
    query = RetrieverQuery(
        question_id="q-1",
        issuer="issuer-northstar",
        query="allocation",
        cutoff=date(2025, 12, 31),
        source_cutoff=date(2025, 6, 30),
    )

    result = run_task8._run_production_retrieval(corpus, graph, (query,))

    assert observed["factory_args"] == (corpus,)
    assert observed["factory_kwargs"] == {
        "cutoff": date(2025, 12, 31),
        "graph": graph,
        "mode": "production",
    }
    assert observed["compare_args"] == (methods, query)
    assert observed["compare_kwargs"] == {"top_k": 5, "final_benchmark": True}
    assert result == {"q-1": {method_id: () for method_id in REGISTERED_METHOD_IDS}}


def test_manifest_contract_and_exact_non_manifest_byte_hashes(
    fixture_release: Path,
) -> None:
    manifest = json.loads((fixture_release / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "task8-manifest.v1"
    assert set(manifest) == {
        "schema_version",
        "repository",
        "run",
        "sources",
        "retrieval",
        "calibration",
        "valuation",
        "attestation",
        "artifacts",
        "limitations",
    }
    assert set(manifest["artifacts"]) == PRINCIPAL_ARTIFACTS - {"manifest.json"}
    for filename, identity in manifest["artifacts"].items():
        data = (fixture_release / filename).read_bytes()
        assert identity["sha256"] == hashlib.sha256(data).hexdigest()
        assert identity["size_bytes"] == len(data)
        assert identity["schema_version"]
    assert "manifest.json" not in manifest["artifacts"]
    assert manifest["retrieval"]["method_ids"] == list(REGISTERED_METHOD_IDS)
    assert manifest["retrieval"]["top_k"] == 5
    assert manifest["run"]["timestamp_policy"] == "frozen_fixture"
    assert manifest["sources"]["question_set_hash"] == hashlib.sha256(
        (REPOSITORY_ROOT / "research" / "questions" / "questions.jsonl").read_bytes()
    ).hexdigest()


def test_fixture_release_uses_fitted_task6_state(fixture_release: Path) -> None:
    manifest = json.loads((fixture_release / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads(
        (fixture_release / "retrieval_summary.json").read_text(encoding="utf-8")
    )
    calibration = manifest["calibration"]

    assert calibration["feature_version"] == "task6-uncertainty-features.v1"
    assert calibration["issuer_split_manifests"]
    assert calibration["coefficients"]
    assert calibration["normalization_state"]
    assert calibration["conformal_thresholds"]
    assert calibration["decision_thresholds"]
    assert all(item["converged"] for item in calibration["convergence"])
    assert manifest["limitations"]["extraction_confidence_proxy"]
    decisions = summary["decision_summary"]
    assert (
        decisions["auto_report_count"]
        + decisions["human_review_required_count"]
        + decisions["insufficient_evidence_count"]
        == summary["question_count"]
    )


def test_fixture_release_uses_explicit_date_valuation_and_canonical_signing(
    fixture_release: Path,
) -> None:
    with (fixture_release / "valuation_sensitivity.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        valuation_rows = list(csv.DictReader(handle))
    assert valuation_rows
    row = valuation_rows[0]
    assert row["status"] == "adjusted"
    assert row["settlement_date"] == "2024-09-15"
    assert row["maturity_date"] == "2030-06-30"
    assert row["day_count_convention"] == "Actual/Actual ICMA"
    assert row["compounding_convention"] == "nominal annual yield compounded at coupon frequency"
    assert float(row["clean_price"]) > 0.0
    assert float(row["dirty_price"]) > 0.0
    assert float(row["modified_duration"]) > 0.0
    assert float(row["convexity"]) > 0.0

    payload = json.loads(
        (fixture_release / "risk_attestation_fixture.json").read_text(encoding="utf-8")
    )
    encoded = payload["attestation"]
    attestation = RiskAttestationV1(
        schema_version=encoded["schemaVersion"],
        asset_id=bytes.fromhex(encoded["assetId"][2:]),
        as_of=encoded["asOf"],
        risk_score_bps=encoded["riskScoreBps"],
        confidence_bps=encoded["confidenceBps"],
        recommended_haircut_bps=encoded["recommendedHaircutBps"],
        evidence_root=bytes.fromhex(encoded["evidenceRoot"][2:]),
        model_version=bytes.fromhex(encoded["modelVersion"][2:]),
        decision_code=encoded["decisionCode"],
        valid_until=encoded["validUntil"],
        nonce=encoded["nonce"],
        provider=encoded["provider"],
    )
    signed = SignedAttestation(
        attestation=attestation,
        signature=bytes.fromhex(payload["signature"][2:]),
        domain_hash=bytes.fromhex(payload["domainSeparator"][2:]),
        struct_hash=bytes.fromhex(payload["structHash"][2:]),
        digest=bytes.fromhex(payload["digest"][2:]),
        signer_address=payload["recoveredProvider"],
        public_key=bytes.fromhex(payload["publicKey"][2:]),
    )
    domain = payload["domain"]
    assert verify_provider(
        signed,
        chain_id=domain["chainId"],
        verifying_contract=domain["verifyingContract"],
        domain_name=domain["name"],
        domain_version=domain["version"],
    )
    assert payload["evidenceRootAlgorithm"] == "sorted-evidence-id-bytes-keccak-merkle-v1"
    assert payload["fixtureSigning"] is True


def test_fixture_artifacts_are_strict_finite_json_and_do_not_expose_keys(
    fixture_release: Path,
) -> None:
    serialized = b"".join(path.read_bytes() for path in sorted(fixture_release.iterdir()))
    lowered = serialized.lower()
    assert b"private_key" not in lowered
    assert b"privatekey" not in lowered
    assert b"nan" not in lowered
    assert b"infinity" not in lowered

    def assert_finite(value: object) -> None:
        if isinstance(value, float):
            assert math.isfinite(value)
        elif isinstance(value, dict):
            for nested in value.values():
                assert_finite(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_finite(nested)

    for path in fixture_release.glob("*.json"):
        assert_finite(json.loads(path.read_text(encoding="utf-8")))


def test_fixture_semantic_output_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for output_dir in (first, second):
        completed = _run_cli(
            "--mode",
            "fixture",
            "--output-dir",
            str(output_dir),
            "--seed",
            "20260710",
        )
        assert completed.returncode == 0, completed.stderr

    assert {
        path.name: path.read_bytes() for path in first.iterdir()
    } == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_fixture_rejects_nonempty_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "stale"
    output_dir.mkdir()
    (output_dir / "stale.txt").write_text("old run", encoding="utf-8")

    completed = _run_cli(
        "--mode",
        "fixture",
        "--output-dir",
        str(output_dir),
        "--seed",
        "20260710",
    )

    assert completed.returncode != 0
    error = json.loads(completed.stderr.strip().splitlines()[-1])
    assert error["code"] == "stale_output_directory"
    assert {path.name for path in output_dir.iterdir()} == {"stale.txt"}


def test_production_rejects_missing_fitted_task6_state() -> None:
    with pytest.raises(run_task8.Task8Error, match="fitted Task 6") as error:
        run_task8._require_fitted_task6_state(())

    assert error.value.code == "unfitted_task6_state"


def test_production_forwards_evidence_location_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[object] = []

    class Metrics:
        recall_at_5 = 0.0
        hit_at_5 = 0.0
        mrr = 0.0
        ndcg_at_5 = 0.0
        temporal_accuracy = 0.0
        stale_evidence_rate = 0.0
        contradiction_f1 = None
        contradiction_evaluable = False
        contradiction_reason = "no_positive_reference_or_prediction"
        citation_accuracy = 0.0
        page_accuracy_at_5 = None
        block_accuracy_at_5 = None
        page_accuracy_reason = "no_gold_page_annotations"
        block_accuracy_reason = "no_gold_block_annotations"
        mismatch_rate = 0.0
        mismatch_denominator = 0

    def fake_score(*args: object, **kwargs: object) -> Metrics:
        observed.append(kwargs["evidence_catalog"])
        return Metrics()

    monkeypatch.setattr("ecoquant.retrieval.evaluation.score_retrieval", fake_score)
    catalog = {"evidence": object()}
    results = {
        "q-1": {method_id: () for method_id in REGISTERED_METHOD_IDS}
    }

    metrics = run_task8._compute_production_metrics(results, object(), catalog)

    assert set(metrics) == set(REGISTERED_METHOD_IDS)
    assert observed == [catalog] * len(REGISTERED_METHOD_IDS)


def test_production_attestation_uses_external_key_and_authoritative_evidence(
    tmp_path: Path,
) -> None:
    from ecdsa import SECP256k1, SigningKey

    from ecoquant.attestation.eip712 import keccak256
    from ecoquant.uncertainty.decision import DecisionCode

    corpus = run_task8.load_production_inputs(_source_cache(tmp_path)).corpus
    private_key = (7).to_bytes(32, "big")
    provider = "0x" + keccak256(
        SigningKey.from_string(private_key, curve=SECP256k1).get_verifying_key().to_string()
    )[-20:].hex()
    signing = run_task8.SigningConfiguration(
        private_key=private_key,
        provider=provider,
        chain_id=31337,
        verifying_contract="0x5FbDB2315678afecb367f032d93F642f64180aa3",
    )

    payload = run_task8._production_attestation(
        corpus=corpus,
        signing=signing,
        seed=20260710,
        decision_code=DecisionCode.AUTO_REPORT,
        recommended_haircut_bps=200,
        source_cutoff=date(2025, 6, 30),
    )

    assert payload["mode"] == "production"
    assert payload["fixtureSigning"] is False
    assert payload["attestation"]["provider"] == provider
    assert payload["recoveredProvider"] == provider
    assert payload["evidenceRootAlgorithm"].startswith("sorted-authoritative")
    assert private_key.hex() not in json.dumps(payload)


def test_production_model_loading_is_forced_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = run_task8.load_production_inputs(_source_cache(tmp_path))
    query = RetrieverQuery(
        question_id="q-1",
        issuer="issuer-northstar",
        query="allocation",
        cutoff=date(2025, 12, 31),
        source_cutoff=date(2025, 6, 30),
    )
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    def fail_factory(*args: object, **kwargs: object) -> tuple:
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
        raise RuntimeError("expected local snapshot blocker")

    monkeypatch.setattr(run_task8, "all_retrievers", fail_factory)

    with pytest.raises(RuntimeError, match="local snapshot blocker"):
        run_task8._run_production_retrieval_with_provenance(
            inputs.corpus,
            inputs.graph,
            (query,),
        )

    assert "HF_HUB_OFFLINE" not in os.environ
    assert "TRANSFORMERS_OFFLINE" not in os.environ
