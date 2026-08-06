"""Adapter: FinVEST experiment -> paper-reproduction-lab manifests (Phase 5.3).

Emits schema-compliant StudyManifest / RunManifest records that bind a FinVEST
experiment's identity, hypothesis, corpus/annotation hashes, methods, metrics,
rerun command, and honest evidence labels.

Constraint (verified): the lab's schemas are RIGID — StudyId is a closed enum
(retrieval / calibration / workflow-agent), seed is fixed to 42, synthetic is
fixed True. So this adapter VALIDATES AND EMITS compliant manifests; it does
NOT drive the lab's runner with FinVEST experiments. The FinVEST A11 pipeline
is a "scoped-claim-check" study (headline_eligible=false), which is exactly
what RunManifest.release_claim encodes.

All lab imports are lazy so CI without the tool repo still passes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def _stable_id(text: str) -> str:
    """Lowercase slug matching ^[a-z0-9]+(?:-[a-z0-9]+)*$."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "finvest"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def emit_study_manifest(
    run_output: dict[str, Any],
    *,
    hypothesis: str,
    corpus_hash: str,
    annotation_version: str = "solo-v1",
    rerun_command: str,
    seed: int = 42,
) -> dict[str, Any]:
    """Emit a schema-compliant StudyManifest for the A11 experiment.

    Maps:
      experiment id      -> study_id (must map to the closed enum; we emit
                            "retrieval" with the FinVEST methods appended)
      hypothesis         -> local_hypothesis
      corpus_hash        -> dataset_id (stable id form)
      methods            -> [R1..R4, S1..S4, V1..V3]
      rerun_command      -> rerun_command
      honest markers     -> evidence_labels=["scoped-claim-check"]

    Returns a dict that validates against paper_reproduction_lab StudyManifest.
    """
    from paper_reproduction_lab.models import (
        EvidenceLabel,
        PaperReference,
        StudyId,
        StudyManifest,
    )

    methods = [
        "r1-bm25", "r2-dense", "r3-rrf", "r4-concept",
        "s1-top-k", "s2-greedy", "s3-beam", "s4-oracle",
        "v1-temporal", "v2-numerical", "v3-joint",
    ]
    metrics = ["recall-at-k", "mrr", "stale-rate", "set-exact-match",
               "redundancy", "numeric-accuracy", "abstention-rate"]

    manifest = StudyManifest(
        study_id=StudyId.RETRIEVAL,
        title="FinVEST leak-free retrieval -> set-selection -> verification",
        evidence_labels=[EvidenceLabel.SCOPED_CLAIM],
        references=[PaperReference(
            reference_id="finvest-a11",
            title="FinVEST evidence-grounded financial QA (internal pilot)",
            authors=["Elian Chyndale"],
            year=2026,
            url="https://github.com/ElianChyndale/EcoQuant-Financial-Intelligence",
            claim_summary=(
                "Solo-provisional pilot: leak-free corpus retrieval + joint "
                "verification. NOT paper results."
            ),
        )],
        local_hypothesis=hypothesis,
        reproduced_mechanics=[
            "leak-free corpus builder (gold-blind)",
            "R1 BM25 / R2 dense / R3 RRF / R4 concept-temporal retrieval",
            "joint temporal/version/numerical verification",
        ],
        not_reproduced=[
            "human double-annotation (single reviewer only)",
            "held-out evaluation on human-validated gold (solo-provisional only)",
        ],
        dataset_id=_stable_id(f"finvest-corpus-{corpus_hash[:12]}"),
        methods=methods,
        metrics=metrics,
        seed=seed,
        rerun_command=rerun_command,
        synthetic=True,
    )
    return manifest.model_dump(mode="json", by_alias=True)


def emit_run_manifest(
    study_manifests: list[dict[str, Any]],
    *,
    corpus_hash: str,
    annotation_hash: str,
    split_hash: str,
    seed: int = 42,
) -> dict[str, Any]:
    """Emit a schema-compliant RunManifest binding dataset + config hashes."""
    from paper_reproduction_lab.models import RunManifest, StudyId

    manifest = RunManifest(
        studies=[StudyId.RETRIEVAL],
        result_count=len(study_manifests),
        dataset_hashes={
            "finvest-corpus": corpus_hash,
            "solo-annotations": annotation_hash,
        },
        config_hashes={
            "split": split_hash,
            "annotation-version": _sha("solo-v1"),
            "seed": str(seed),
        },
        seed=seed,
    )
    return manifest.model_dump(mode="json", by_alias=True)


def write_manifests(
    run_output: dict[str, Any],
    *,
    output_dir: Any,
    corpus_hash: str,
    annotation_hash: str,
    split_hash: str,
    hypothesis: str,
    rerun_command: str,
) -> dict[str, Any]:
    """Emit and persist StudyManifest + RunManifest to output_dir.

    Returns the written manifest dict (study + run). Validates against the lab
    models before writing (raise on schema violation).
    """
    import json as _json
    from pathlib import Path

    from paper_reproduction_lab.models import RunManifest, StudyManifest

    study = StudyManifest(**emit_study_manifest(
        run_output, hypothesis=hypothesis, corpus_hash=corpus_hash,
        rerun_command=rerun_command,
    ))
    run = RunManifest(**emit_run_manifest(
        [study.model_dump(mode="json", by_alias=True)],
        corpus_hash=corpus_hash, annotation_hash=annotation_hash,
        split_hash=split_hash,
    ))

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "study-manifest.json").write_text(
        _json.dumps(study.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out / "run-manifest.json").write_text(
        _json.dumps(run.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "study_manifest": study.model_dump(mode="json", by_alias=True),
        "run_manifest": run.model_dump(mode="json", by_alias=True),
        "output_dir": str(out),
    }
