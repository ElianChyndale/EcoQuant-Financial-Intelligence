"""One-command E5 calibration + selective prediction over FinanceBench retrieval.

Usage: python scripts/run_e5_calibration.py
Reruns the E1 FinanceBench retrieval baselines, builds the five uncertainty
features per (question, method), fits nested leave-one-company-out calibration
folds, and reports selective-prediction metrics (ECE, Brier, AUROC, coverage at
90%/95% precision, risk-coverage frontier). Writes
research/results/e5_calibration_summary.json. Exits 0 iff evaluation completed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/results/e5_calibration_summary.json"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))

    from ecoquant.research.calibration_eval.evaluate import evaluate_selective_folds
    from ecoquant.research.calibration_eval.features import build_features_from_retrieval
    from ecoquant.research.datasets.financebench import load_financebench
    from ecoquant.research.retrieval_eval.baselines import run_baselines
    from ecoquant.research.retrieval_eval.corpora import build_financebench_corpus

    bundle = load_financebench(
        questions_path=ROOT / "research/cache/financebench/financebench_open_source.jsonl",
        docs_path=ROOT / "research/cache/financebench/financebench_document_information.jsonl",
    )
    corpus, catalog, gold = build_financebench_corpus(bundle)
    method_results = run_baselines(corpus, bundle.public_cases)

    # Build {company: (features, labels)} from the retrieval results.
    fold_data: dict[str, tuple[list, list]] = {}
    for company in sorted({case.issuer for case in bundle.public_cases}):
        company_questions = {
            qid: relevant
            for qid, relevant in gold.relevant_evidence.items()
            if gold.issuer_by_question[qid] == company
        }
        company_results = {
            method: {qid: ranked for qid, ranked in by_question.items() if qid in company_questions}
            for method, by_question in method_results.items()
        }
        features, labels = build_features_from_retrieval(company_results, company_questions)
        if features:
            fold_data[company] = (features, labels)

    result = evaluate_selective_folds(fold_data)
    payload = {
        "experiment": "e5-calibration-selective",
        "note": (
            "Calibration over E1 FinanceBench retrieval results (150 questions, "
            "6 methods). Features: retrieval margin, cross-retriever agreement, "
            "extraction confidence, temporal validity, evidence coverage. "
            "Nested leave-one-company-out folds; held-out pooled metrics."
        ),
        "dataset": {
            "question_count": len(bundle.public_cases),
            "company_count": len(fold_data),
            "feature_record_count": sum(len(f) for f, _ in fold_data.values()),
        },
        "metrics": result,
        "all_ok": bool("ece" in result and "brier" in result),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
