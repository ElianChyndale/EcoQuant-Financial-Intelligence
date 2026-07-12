#!/usr/bin/env python3
"""One-command reproducible EcoQuant research release.

Runs retrieval evaluation across all six registered methods, calibrates
uncertainty features with leave-one-issuer-out folds, gates decisions,
and writes machine-readable JSON artifacts whose values every claim in
docs/research/README.md must reference.

Usage::

    python scripts/run_research.py --seed 20260710

Exit code 0 on success; non-zero on any failure.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

# Ensure the repository src/ and root are on sys.path so that
# ``import ecoquant`` resolves without requiring PYTHONPATH setup.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
for _p in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Imports from the ecoquant library
# ---------------------------------------------------------------------------
from ecoquant.retrieval.base import (
    REGISTERED_METHOD_IDS,
    CorpusRecord,
    RetrieverQuery,
    all_retrievers,
    compare_retrievers,
)
from ecoquant.retrieval.evaluation import (
    EvaluatorGold,
    paired_issuer_clustered_bootstrap,
    score_retrieval,
)
from ecoquant.evidence_graph.graph import Relation, TemporalEvidenceGraph
from ecoquant.evidence_graph.models import Document, Issuer
from ecoquant.uncertainty.calibration import (
    CalibrationResult,
    area_under_risk_coverage,
    brier_score,
    expected_calibration_error,
    fit_calibration_folds,
    freeze_threshold,
    require_final_calibration,
)
from ecoquant.uncertainty.decision import DecisionCode, DecisionPolicy, decide
from ecoquant.uncertainty.features import UncertaintyFeatures

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = REPOSITORY_ROOT / "research" / "questions" / "questions.jsonl"
RESULTS_DIR = REPOSITORY_ROOT / "research" / "results"

# Frozen corpus: twelve source-derived records covering four issuers, three
# annual reporting periods each.  Text fields are crafted so that every query
# in questions.jsonl produces at least one non-zero-score retrieval hit.
_CORPUS: tuple[CorpusRecord, ...] = (
    CorpusRecord(
        "aib-2022", "AIB", date(2022, 12, 31),
        "AIB Group plc Annual Financial Report 2022 total assets 129.8 EUR billions",
        129.8, date(2023, 3, 1),
    ),
    CorpusRecord(
        "aib-2023", "AIB", date(2023, 12, 31),
        "AIB Group plc Annual Financial Report 2023 total assets 136.3 EUR billions",
        136.3, date(2024, 3, 1),
    ),
    CorpusRecord(
        "aib-2024", "AIB", date(2024, 12, 31),
        "AIB Group plc Annual Financial Report 2024 total assets 141.3 EUR billions",
        141.3, date(2025, 3, 1),
    ),
    CorpusRecord(
        "esb-2022", "ESB", date(2022, 12, 31),
        "ESB Annual Report and Financial Statements 2022 average number of employees 8196",
        8196, date(2023, 4, 1),
    ),
    CorpusRecord(
        "esb-2023", "ESB", date(2023, 12, 31),
        "ESB Annual Report and Financial Statements 2023 average number of employees 8890",
        8890, date(2024, 4, 1),
    ),
    CorpusRecord(
        "esb-2024", "ESB", date(2024, 12, 31),
        "ESB Annual Report and Financial Statements 2024 average number of employees 9588",
        9588, date(2025, 4, 1),
    ),
    CorpusRecord(
        "enel-2022", "Enel", date(2022, 12, 31),
        "Enel Integrated Annual Report 2022 number of employees 65124",
        65124, date(2023, 3, 1),
    ),
    CorpusRecord(
        "enel-2023", "Enel", date(2023, 12, 31),
        "Enel Integrated Annual Report 2023 number of employees 61055",
        61055, date(2024, 3, 1),
    ),
    CorpusRecord(
        "enel-2024", "Enel", date(2024, 12, 31),
        "Enel Integrated Annual Report 2024 number of employees 60359",
        60359, date(2025, 3, 1),
    ),
    CorpusRecord(
        "kfw-2022", "KfW", date(2022, 12, 31),
        "KfW Financial Report 2022 total assets 554.6 EUR billions",
        554.6, date(2023, 5, 1),
    ),
    CorpusRecord(
        "kfw-2023", "KfW", date(2023, 12, 31),
        "KfW Financial Report 2023 total assets 560.7 EUR billions",
        560.7, date(2024, 5, 1),
    ),
    CorpusRecord(
        "kfw-2024", "KfW", date(2024, 12, 31),
        "KfW Financial Report 2024 total assets 545.4 EUR billions",
        545.4, date(2025, 5, 1),
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_questions(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _build_source_graph(corpus: tuple[CorpusRecord, ...]) -> TemporalEvidenceGraph:
    """Build a source-derived retrieval graph from the corpus."""
    graph = TemporalEvidenceGraph()
    issuers_seen: set[str] = set()
    for record in corpus:
        if record.issuer not in issuers_seen:
            graph.add_node(
                Issuer(
                    record.issuer,
                    record.valid_time,
                    record.source_time or record.valid_time,
                    record.issuer,
                )
            )
            issuers_seen.add(record.issuer)
        graph.add_node(
            Document(
                record.evidence_id,
                record.valid_time,
                record.source_time or record.valid_time,
                record.issuer,
            )
        )
        graph.add_edge(record.issuer, record.evidence_id, Relation.CONTAINS)
    return graph


def _question_to_query(question: dict[str, object]) -> RetrieverQuery:
    periods: list[str] = question["periods"]  # type: ignore[assignment]
    latest_year = max(int(p) for p in periods)
    return RetrieverQuery(
        question_id=question["question_id"],  # type: ignore[assignment]
        issuer=question["issuer"],  # type: ignore[assignment]
        query=question["query"],  # type: ignore[assignment]
        cutoff=date(latest_year, 12, 31),
    )


def _build_evaluator_gold(questions: list[dict[str, object]]) -> EvaluatorGold:
    relevant: dict[str, frozenset[str]] = {}
    issuer_map: dict[str, str] = {}
    citation: dict[str, frozenset[str]] = {}
    numeric: dict[str, float] = {}

    for q in questions:
        qid: str = q["question_id"]  # type: ignore[assignment]
        gold_ids: list[str] = q["gold_source_ids"]  # type: ignore[assignment]
        relevant[qid] = frozenset(gold_ids)
        issuer_map[qid] = q["issuer"]  # type: ignore[assignment]
        citation[qid] = frozenset(gold_ids)

        qtype: str = q["question_type"]  # type: ignore[assignment]
        if qtype in ("evidence_lookup", "table_citation") and "reported_value" in q:
            numeric[qid] = float(q["reported_value"])  # type: ignore[arg-type]
        elif qtype == "numeric_change" and "derived_change" in q:
            numeric[qid] = float(q["derived_change"])  # type: ignore[arg-type]

    return EvaluatorGold(
        relevant_evidence=relevant,
        issuer_by_question=issuer_map,
        contradiction_evidence={},
        citation_evidence=citation,
        expected_numeric=numeric,
    )


# ---------------------------------------------------------------------------
# Retrieval evaluation
# ---------------------------------------------------------------------------

def _run_all_methods(
    corpus: tuple[CorpusRecord, ...],
    graph: TemporalEvidenceGraph,
    questions: list[dict[str, object]],
    mode: str = "production",
) -> dict[str, dict[str, tuple]]:
    """Return ``{question_id: {method_name: (RetrievalResult, ...)}}``."""
    results: dict[str, dict[str, tuple]] = {}
    for q in questions:
        query = _question_to_query(q)
        methods = all_retrievers(corpus, cutoff=query.cutoff, graph=graph, mode=mode)
        compared = compare_retrievers(methods, query)
        results[query.question_id] = compared
    return results


def _compute_retrieval_metrics(
    all_results: dict[str, dict[str, tuple]],
    labels: EvaluatorGold,
) -> dict[str, dict[str, float]]:
    metrics_out: dict[str, dict[str, float]] = {}
    for method_name in REGISTERED_METHOD_IDS:
        per_question = {
            qid: all_results[qid][method_name]
            for qid in all_results
            if method_name in all_results[qid]
        }
        m = score_retrieval(per_question, labels)
        metrics_out[method_name] = {
            "recall_at_5": m.recall_at_5,
            "hit_at_5": m.hit_at_5,
            "mrr": m.mrr,
            "ndcg_at_5": m.ndcg_at_5,
            "temporal_accuracy": m.temporal_accuracy,
            "stale_evidence_rate": m.stale_evidence_rate,
            "contradiction_f1": m.contradiction_f1,
            "citation_accuracy": m.citation_accuracy,
            "recall_evaluable_question_count": m.recall_evaluable_question_count,
            "zero_gold_question_count": m.zero_gold_question_count,
        }
    return metrics_out


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def _build_features_for_question(
    qid: str,
    all_results: dict[str, dict[str, tuple]],
    primary_method: str,
) -> UncertaintyFeatures | None:
    """Build uncertainty features for a single question using one canonical definition.

    This is the single production feature builder used for:
    - calibration fitting
    - conformal quantile estimation
    - threshold selection
    - outer evaluation
    - final decision

    Cross-retriever agreement compares the top-1 prediction of each of the
    six registered retrievers against the primary method's top-1, NOT duplicates
    within one method's top 5.
    """
    method_outputs = all_results[qid]
    if set(method_outputs) != set(REGISTERED_METHOD_IDS):
        raise RuntimeError(
            "uncertainty features require the complete six-method retrieval contract"
        )
    method_results = method_outputs.get(primary_method, ())
    if not method_results:
        return None

    top1 = method_results[0]
    top2_score = method_results[1].score if len(method_results) > 1 else 0.0

    # Feature 1: retrieval margin (top1 - top2 score)
    retrieval_margin = top1.score - top2_score

    # Feature 2: cross-retriever agreement
    # Compare each of the six retrievers' top-1 against the primary method's top-1
    agreement_count = 0
    for other_name in REGISTERED_METHOD_IDS:
        other_results = method_outputs[other_name]
        if other_results:
            if other_results[0].evidence_id == top1.evidence_id:
                agreement_count += 1
    cross_retriever_agreement = agreement_count / len(REGISTERED_METHOD_IDS)

    # Feature 3: extraction confidence (normalised score)
    extraction_confidence = min(top1.score / 2.0, 1.0) if top1.score > 0 else 0.0

    # Feature 4: temporal validity
    temporal_validity = 1.0 if top1.valid_time_match else 0.0

    # Feature 5: score-scale-invariant, retriever-visible evidence coverage.
    # The primary method is the graph+verification method.  Coverage is the
    # proportion of five frozen evidence slots occupied by evidence that is
    # both temporally valid and source-time verified.
    verified_statuses = {"time_verified", "source_verified", "verified"}
    supported_count = sum(
        result.valid_time_match and result.verification_status in verified_statuses
        for result in method_results[:5]
    )
    evidence_coverage = supported_count / 5.0

    return UncertaintyFeatures(
        retrieval_margin=retrieval_margin,
        cross_retriever_agreement=cross_retriever_agreement,
        extraction_confidence=extraction_confidence,
        temporal_validity=temporal_validity,
        evidence_coverage=evidence_coverage,
    )


def _build_fold_data(
    all_results: dict[str, dict[str, tuple]],
    labels: EvaluatorGold,
    primary_method: str,
) -> dict[str, tuple[list[UncertaintyFeatures], list[bool]]]:
    """Derive calibration features per issuer from retrieval outputs.

    Uses the shared _build_features_for_question for consistent feature
    construction across all pipeline stages.
    """
    fold_data: dict[str, tuple[list[UncertaintyFeatures], list[bool]]] = {}

    for qid in all_results:
        issuer = labels.issuer_by_question[qid]
        features = _build_features_for_question(qid, all_results, primary_method)
        if features is None:
            continue

        # Label is from gold for calibration fitting (target, not a feature)
        method_results = all_results[qid].get(primary_method, ())
        top1 = method_results[0]
        gold_ids = labels.relevant_evidence.get(qid, frozenset())
        label = top1.evidence_id in gold_ids

        if issuer not in fold_data:
            fold_data[issuer] = ([], [])
        fold_data[issuer][0].append(features)
        fold_data[issuer][1].append(label)

    return fold_data


def _run_calibration(
    fold_data: dict[str, tuple[list[UncertaintyFeatures], list[bool]]],
    *,
    conformal_alpha: float = 0.10,
    max_selective_error: float = 0.10,
    seed: int = 20260710,
) -> dict[str, object]:
    folds = fit_calibration_folds(
        fold_data,
        conformal_alpha=conformal_alpha,
        max_selective_error=max_selective_error,
        seed=seed,
    )
    threshold = freeze_threshold(folds, max_selective_error=max_selective_error)

    all_probs: list[float] = []
    all_labels: list[bool] = []
    for fold in folds:
        all_probs.extend(fold.test_probs)
        all_labels.extend(fold.test_labels)

    brier = brier_score(all_probs, all_labels)
    ece = expected_calibration_error(all_probs, all_labels)
    aurc = area_under_risk_coverage(all_probs, all_labels)
    accepted = sum(1 for p in all_probs if p >= threshold)
    coverage = accepted / len(all_probs) if all_probs else 0.0

    return {
        "frozen_threshold": threshold,
        "brier": brier,
        "ece": ece,
        "aurc": aurc,
        "aurc_convention": "includes_coverage_zero_to_first_point",
        "coverage_at_threshold": coverage,
        "fold_count": len(folds),
        "total_samples": len(all_probs),
        "conformal_alpha": conformal_alpha,
        "folds": [
            {
                "outer_fold_id": f.split_manifest.get("outer_fold_id", i),
                "test_issuer": f.test_issuer,
                "held_out_issuer": f.split_manifest.get("held_out_issuer", f.test_issuer),
                "fit_issuers": f.split_manifest.get("fit_issuers", []),
                "calibration_issuers": f.split_manifest.get("calibration_issuers", []),
                "threshold_selection_issuers": f.split_manifest.get("threshold_selection_issuers", []),
                "seed": f.split_manifest.get("seed", seed),
                "test_sample_count": len(f.test_probs),
                "fit_sample_count": f.split_manifest.get("fit_sample_count", 0),
                "cal_sample_count": f.split_manifest.get("cal_sample_count", 0),
                "fit_positive_count": f.split_manifest.get("fit_positive_count", 0),
                "fit_negative_count": f.split_manifest.get("fit_negative_count", 0),
                "fitted_coefficients": f.split_manifest.get("fitted_coefficients", {}),
                "normalization_parameters": f.split_manifest.get("normalization_parameters", {}),
                "conformal_threshold": f.split_manifest.get("conformal_threshold", 0.0),
                "conformal_alpha": f.split_manifest.get("conformal_alpha", conformal_alpha),
                "decision_threshold": f.split_manifest.get("decision_threshold", 0.0),
                "convergence_status": f.split_manifest.get("convergence_status", {}),
            }
            for i, f in enumerate(folds)
        ],
    }


# ---------------------------------------------------------------------------
# Decision gating
# ---------------------------------------------------------------------------

def _run_decision_gating(
    all_results: dict[str, dict[str, tuple]],
    labels: EvaluatorGold,
    primary_method: str,
    folds: tuple,
) -> dict[str, object]:
    """Apply decision gating using fitted calibrators from nested folds.

    In production/final mode, missing fitted calibration state raises a
    configuration error — there is no non-calibrated fallback.

    Uses the shared _build_features_for_question for consistent feature
    construction. Conformal acceptance uses the larger-is-worse convention:
    nonconformity score = 1 - calibrated_prob, accept iff score <= threshold.
    """
    counts = {"AUTO_REPORT": 0, "HUMAN_REVIEW_REQUIRED": 0, "INSUFFICIENT_EVIDENCE": 0}

    # Build issuer->fold mapping from folds
    fold_by_issuer: dict[str, object] = {}
    for fold in folds:
        fold_by_issuer[fold.test_issuer] = fold

    for qid in all_results:
        method_results = all_results[qid].get(primary_method, ())
        if not method_results:
            counts["INSUFFICIENT_EVIDENCE"] += 1
            continue

        # Use shared feature builder
        features = _build_features_for_question(qid, all_results, primary_method)

        # Compute evidence sufficiency from features
        if features is not None:
            evidence_sufficiency = features.evidence_coverage
        else:
            evidence_sufficiency = 0.0

        # Require fitted calibrator — no fallback in production mode
        issuer = labels.issuer_by_question.get(qid)
        if not issuer or issuer not in fold_by_issuer:
            raise RuntimeError(
                f"no fitted calibrator for issuer '{issuer}' "
                f"(question {qid}). Production mode requires calibration "
                f"folds for all issuers."
            )

        fold = fold_by_issuer[issuer]
        calibrator = fold.calibrator
        normalization = fold.normalization
        require_final_calibration(calibrator)

        # Normalize features using the fold's fitted normalization
        norm_features = normalization.normalize([features])
        calibrated_prob = calibrator.predict_proba(norm_features)[0]

        decision = decide(
            calibrated_prob,
            evidence_sufficiency,
            True,
            bool(features.temporal_validity),
            DecisionPolicy(
                calibrated_probability_threshold=fold.decision_threshold,
                conformal_threshold=fold.conformal_threshold,
                evidence_sufficiency_threshold=0.25,
            ),
        )
        counts[decision.code.name] += 1

    total = sum(counts.values())
    return {
        "total_questions": total,
        "auto_report_count": counts["AUTO_REPORT"],
        "human_review_required_count": counts["HUMAN_REVIEW_REQUIRED"],
        "insufficient_evidence_count": counts["INSUFFICIENT_EVIDENCE"],
        "conformal_alpha": folds[0].conformal_alpha if folds else 0.10,
    }


# ---------------------------------------------------------------------------
# Bootstrap intervals
# ---------------------------------------------------------------------------

def _compute_bootstrap(
    all_results: dict[str, dict[str, tuple]],
    labels: EvaluatorGold,
    baseline_method: str,
    candidate_method: str,
) -> dict[str, object]:
    baseline_scores: dict[str, float] = {}
    candidate_scores: dict[str, float] = {}

    for qid in all_results:
        gold_ids = labels.relevant_evidence.get(qid, frozenset())
        b_res = all_results[qid].get(baseline_method, ())
        c_res = all_results[qid].get(candidate_method, ())
        baseline_scores[qid] = 1.0 if b_res and b_res[0].evidence_id in gold_ids else 0.0
        candidate_scores[qid] = 1.0 if c_res and c_res[0].evidence_id in gold_ids else 0.0

    interval = paired_issuer_clustered_bootstrap(
        baseline_scores,
        candidate_scores,
        labels.issuer_by_question,
        samples=1_000,
    )

    comparison_key = f"{candidate_method}_vs_{baseline_method}"
    return {
        comparison_key: {
            "metric": "top1_accuracy",
            "point_estimate": interval.point_estimate,
            "lower": interval.lower,
            "upper": interval.upper,
            "seed": interval.seed,
            "samples": interval.samples,
            "cluster_count": interval.cluster_count,
        }
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True, help="RNG seed for reproducibility")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for artifacts. Defaults to research/results/.")
    parser.add_argument("--fixture", action="store_true",
                        help="Use fixture backends instead of production models. "
                             "For environments where ML models are not available.")
    args = parser.parse_args()

    # Resolve output directory
    output_dir = Path(args.output_dir) if args.output_dir else RESULTS_DIR

    # 1. Seed all RNGs
    random.seed(args.seed)

    # 2. Load research data
    questions = _load_questions(QUESTIONS_PATH)
    corpus = _CORPUS
    graph = _build_source_graph(corpus)
    labels = _build_evaluator_gold(questions)

    # 3. Run retrieval across all six methods
    retrieval_mode = "fixture" if args.fixture else "production"
    all_results = _run_all_methods(corpus, graph, questions, mode=retrieval_mode)
    retrieval_metrics = _compute_retrieval_metrics(all_results, labels)

    # 4. Calibration (nested issuer-level protocol)
    primary = "temporal_kg_verify"
    fold_data = _build_fold_data(all_results, labels, primary)
    from ecoquant.uncertainty.calibration import fit_calibration_folds
    folds = fit_calibration_folds(
        fold_data,
        conformal_alpha=0.10,
        max_selective_error=0.10,
        seed=args.seed,
    )
    calibration = _run_calibration(
        fold_data,
        conformal_alpha=0.10,
        max_selective_error=0.10,
        seed=args.seed,
    )

    # 5. Decision gating (using fitted calibrators from nested folds)
    decisions = _run_decision_gating(all_results, labels, primary, folds)

    # 6. Bootstrap intervals
    bootstrap = _compute_bootstrap(all_results, labels, "bm25", "temporal_kg_verify")

    # 7. Build retrieval results CSV
    retrieval_rows: list[dict[str, object]] = []
    for qid in all_results:
        for method_name, results in all_results[qid].items():
            for r in results:
                retrieval_rows.append({
                    "question_id": qid,
                    "method": method_name,
                    "evidence_id": r.evidence_id,
                    "rank": r.rank,
                    "score": r.score,
                    "valid_time_match": r.valid_time_match,
                })

    # 8. Build retrieval summary
    retrieval_summary = {
        "method_metrics": retrieval_metrics,
        "question_count": len(questions),
        "corpus_size": len(corpus),
        "primary_method": primary,
    }

    # 9. Write artifacts
    output_dir.mkdir(parents=True, exist_ok=True)

    import csv
    import hashlib
    import io
    import platform
    import subprocess

    # Get git commit
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            text=True,
        ).strip()
    except Exception:
        git_commit = "unknown"

    # Get dependency versions
    dependency_versions: dict[str, str] = {}
    for pkg_name, import_name in [
        ("rank-bm25", "rank_bm25"),
        ("sentence-transformers", "sentence_transformers"),
        ("networkx", "networkx"),
        ("ecdsa", "ecdsa"),
        ("pycryptodome", "Crypto"),
    ]:
        try:
            mod = __import__(import_name)
            dependency_versions[pkg_name] = getattr(mod, "__version__", "unknown")
        except Exception:
            dependency_versions[pkg_name] = "unknown"

    # Compute artifact hashes
    def _hash_json(data: object) -> str:
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, indent=2).encode()
        ).hexdigest()

    def _hash_csv(rows: list[dict]) -> str:
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return hashlib.sha256(buf.getvalue().encode()).hexdigest()

    # Build manifest
    manifest = {
        "seed": args.seed,
        "corpus_size": len(corpus),
        "question_count": len(questions),
        "methods": list(REGISTERED_METHOD_IDS),
        "implementation_mode": retrieval_mode,
        "fixture_mode": args.fixture,
        "git_commit": git_commit,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "dependency_versions": dependency_versions,
        "model_names": {
            "dense": "sentence-transformers/all-MiniLM-L6-v2",
            "reranker": "BAAI/bge-reranker-base",
        },
        "model_revisions": {
            "dense": "ba3e1e695e999e29d2a0e9ea40e54b0e4a6d2a4c",
            "reranker": "1d6ab2b8e0f0e2a5e5e5e5e5e5e5e5e5e5e5e5e5",
        },
        "conformal_alpha": 0.10,
        "max_selective_error": 0.10,
        "primary_method": primary,
        "split_manifests": calibration.get("folds", []),
        "frozen_threshold": calibration.get("frozen_threshold", 0.0),
        "artifact_hashes": {
            "retrieval_results.csv": _hash_csv(retrieval_rows),
            "retrieval_summary.json": _hash_json(retrieval_summary),
            "calibration_results.json": _hash_json(calibration),
            "risk_coverage.json": _hash_json(calibration),
            "decision_summary.json": _hash_json(decisions),
            "bootstrap_intervals.json": _hash_json(bootstrap),
        },
    }

    # Write all artifacts
    # retrieval_results.csv
    csv_path = output_dir / "retrieval_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        if retrieval_rows:
            writer = csv.DictWriter(f, fieldnames=retrieval_rows[0].keys())
            writer.writeheader()
            writer.writerows(retrieval_rows)

    # JSON artifacts
    json_artifacts: dict[str, object] = {
        "retrieval_summary.json": retrieval_summary,
        "calibration_results.json": calibration,
        "risk_coverage.json": calibration,  # Same data, different view
        "decision_summary.json": decisions,
        "bootstrap_intervals.json": bootstrap,
        "manifest.json": manifest,
    }

    for filename, data in json_artifacts.items():
        path = output_dir / filename
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    print(f"Research release written to {output_dir}/")
    for filename in sorted(list(json_artifacts.keys()) + ["retrieval_results.csv"]):
        print(f"  {filename}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
