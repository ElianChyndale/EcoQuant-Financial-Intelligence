"""One-command E1 retrieval evaluation over FinanceBench + EcoQuant corpus.

Usage: python scripts/run_e1_retrieval.py
Writes research/results/e1_retrieval_summary.json with per-method metrics and
company/issuer-clustered bootstrap CIs. Exits 0 iff all methods scored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/results/e1_retrieval_summary.json"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))

    from ecoquant.retrieval.evaluation import paired_issuer_clustered_bootstrap, score_retrieval
    from ecoquant.research.datasets.ecoquant_corpus import load_ecoquant_corpus
    from ecoquant.research.datasets.financebench import load_financebench
    from ecoquant.research.retrieval_eval.baselines import run_baselines
    from ecoquant.research.retrieval_eval.corpora import build_ecoquant_corpus, build_financebench_corpus

    financebench_bundle = load_financebench(
        questions_path=ROOT / "research/cache/financebench/financebench_open_source.jsonl",
        docs_path=ROOT / "research/cache/financebench/financebench_document_information.jsonl",
    )
    ecoquant_bundle = load_ecoquant_corpus(
        questions_path=ROOT / "research/questions/questions.jsonl",
        manifest_path=ROOT / "research/sources/source_manifest.csv",
    )

    fb_corpus, fb_catalog, fb_gold = build_financebench_corpus(financebench_bundle)
    eq_corpus, eq_catalog, eq_gold = build_ecoquant_corpus(ecoquant_bundle)

    datasets = {
        "financebench": (financebench_bundle.public_cases, fb_corpus, fb_catalog, fb_gold),
        "ecoquant_corpus": (ecoquant_bundle.public_cases, eq_corpus, eq_catalog, eq_gold),
    }

    results_by_dataset: dict[str, dict[str, object]] = {}
    for dataset_name, (queries, corpus, catalog, gold) in datasets.items():
        method_results = run_baselines(corpus, queries)
        scored: dict[str, object] = {}
        for method, by_question in method_results.items():
            metrics = score_retrieval(by_question, gold, evidence_catalog=catalog)
            # Bootstrap CI on the primary metric (Recall@5) by resampling issuer clusters.
            recall_by_question = _per_question_recall(by_question, gold)
            interval = paired_issuer_clustered_bootstrap(
                {qid: 0.0 for qid in recall_by_question},
                recall_by_question,
                gold.issuer_by_question,
                samples=1000,
            )
            scored[method] = {
                "recall_at_5": metrics.recall_at_5,
                "hit_at_5": metrics.hit_at_5,
                "mrr": metrics.mrr,
                "ndcg_at_5": metrics.ndcg_at_5,
                "page_accuracy_at_5": metrics.page_accuracy_at_5,
                "bootstrap_ci_95": {
                    "lower": interval.lower,
                    "point_estimate": interval.point_estimate,
                    "upper": interval.upper,
                    "seed": interval.seed,
                    "samples": interval.samples,
                    "cluster_count": interval.cluster_count,
                },
            }
        results_by_dataset[dataset_name] = {
            "question_count": len(queries),
            "corpus_size": len(corpus),
            "methods": scored,
        }

    payload = {
        "experiment": "e1-retrieval-baselines",
        "note": (
            "B6 (cross-encoder reranker) remains blocked by external model assets; "
            "dense uses locally cached all-MiniLM-L6-v2. FinanceBench evidence is "
            "cache-only; EcoQuant corpus is the frozen 64-question corpus."
        ),
        "datasets": results_by_dataset,
        "all_ok": all(methods for ds in results_by_dataset.values() for methods in [ds["methods"]]),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


def _per_question_recall(
    by_question: dict[str, object],
    gold: object,
) -> dict[str, float]:
    """Per-question Recall@5 for bootstrap resampling."""
    per_q: dict[str, float] = {}
    for question_id, ranked in by_question.items():
        relevant = gold.relevant_evidence[question_id]
        retrieved = {result.evidence_id for result in ranked}
        if relevant:
            per_q[question_id] = len(retrieved & relevant) / len(relevant)
        else:
            per_q[question_id] = 0.0
    return per_q


if __name__ == "__main__":
    raise SystemExit(main())
