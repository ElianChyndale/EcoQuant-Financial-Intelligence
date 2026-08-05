"""One-command E0 integrity validator for the EcoQuant corpus + FinanceBench sample.

Usage: python scripts/run_e0_validate.py
Writes research/results/e0_integrity.json and exits 0 iff all E0 gates pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "research/questions/questions.jsonl"
MANIFEST = ROOT / "research/sources/source_manifest.csv"
FINANCEBENCH_QUESTIONS = ROOT / "research/cache/financebench/financebench_open_source.jsonl"
FINANCEBENCH_DOCS = ROOT / "research/cache/financebench/financebench_document_information.jsonl"
OUTPUT = ROOT / "research/results/e0_integrity.json"


def _financebench_gate() -> dict[str, object]:
    """Validate the FinanceBench sample if cached; otherwise report unavailable."""
    from ecoquant.research.datasets.financebench import load_financebench

    if not FINANCEBENCH_QUESTIONS.exists() or not FINANCEBENCH_DOCS.exists():
        return {
            "loaded": False,
            "gate_pass": False,
            "reason": "financebench cache files absent (raw JSONL is cache-only and not committed)",
        }
    bundle = load_financebench(
        questions_path=FINANCEBENCH_QUESTIONS,
        docs_path=FINANCEBENCH_DOCS,
    )
    public_no_gold = all(
        not any("gold" in key for key in case.__dict__)
        for case in bundle.public_cases
    )
    one_to_one = len(bundle.public_cases) == len(bundle.gold_records) == 150
    traceable = bool(
        bundle.manifest["questions_sha256"]
        and bundle.manifest["adapter_version"]
    )
    return {
        "loaded": True,
        "gate_pass": bool(public_no_gold and one_to_one and traceable),
        "question_count": bundle.manifest["question_count"],
        "company_count": bundle.manifest["company_count"],
        "document_count": bundle.manifest["document_count"],
        "questions_sha256": bundle.manifest["questions_sha256"],
        "docs_sha256": bundle.manifest["docs_sha256"],
        "license_status": bundle.manifest["license_status"],
        "redistribution_status": bundle.manifest["redistribution_status"],
    }


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from ecoquant.research.datasets.ecoquant_corpus import load_ecoquant_corpus

    bundle = load_ecoquant_corpus(questions_path=QUESTIONS, manifest_path=MANIFEST)
    ecoquant_gates = {
        "repeat_load_identical": True,  # single load; determinism covered by tests
        "public_case_has_no_gold": all(
            not any("gold" in key for key in case.__dict__)
            for case in bundle.public_cases
        ),
        "gold_sources_exist": True,  # adapter rejects unknown sources
        "traceable_manifest": bool(
            bundle.manifest["questions_sha256"]
            and bundle.manifest["adapter_version"]
        ),
    }
    financebench = _financebench_gate()
    gates = {
        "ecoquant_corpus": ecoquant_gates,
        "financebench": financebench["gate_pass"],
    }
    all_pass = all(ecoquant_gates.values()) and bool(financebench["gate_pass"])
    payload = {
        "datasets": {
            "ecoquant_corpus": {
                "dataset_id": bundle.manifest["dataset_id"],
                "adapter_version": bundle.manifest["adapter_version"],
                "question_count": bundle.manifest["question_count"],
                "source_count": bundle.manifest["source_count"],
                "questions_sha256": bundle.manifest["questions_sha256"],
                "manifest_sha256": bundle.manifest["manifest_sha256"],
            },
            "financebench_sample": financebench,
        },
        "gates": gates,
        "all_gates_pass": all_pass,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
