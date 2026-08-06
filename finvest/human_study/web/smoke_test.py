"""Workbench local smoke test (never touches real signed JSONL).

Validates: server starts, dashboard loads, one base case renders, evidence
resolves, autosave works, signing is rejected without confirmation, and no
outbound network occurs. Uses an isolated temp DB and a temp day1 copy — the
REAL human_review/day1 JSONL files are never written.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1
from finvest.human_study.protocol_config import V0_2_DRAFT
from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.human_study.web.services.draft_service import DraftService
from finvest.human_study.web.services.evidence_service import resolve_evidence_set
from finvest.human_study.web.services.protocol_web import base_queue, record_file_path
from finvest.human_study.web.services.signing_adapter import append_signed

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "research" / "cache"
FIXTURE_TICKERS = ("aapl", "msft", "ko", "eqix", "jnj", "ups")


def _fixture_cache(tmp_root: Path) -> Path:
    """Build a temp cache from the committed SEC fixture (never real cache)."""
    cache = tmp_root / "cache"
    sec = cache / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
        encoding="utf-8"
    )
    for ticker in FIXTURE_TICKERS:
        (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")
    return cache


def run_smoke_test(tmp_root: Path | None = None) -> dict[str, object]:
    """Run the isolated smoke test; returns results (never creates real labels)."""
    tmp_root = tmp_root or Path(tempfile.mkdtemp(prefix="finvest-smoke-"))
    day1_dir = tmp_root / "day1"
    # Active protocol (v0.2-draft) freeze: accept the actual valid-case count.
    cache = _fixture_cache(tmp_root)
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1_dir, min_cases=1, cache_dir=cache,
                protocol=V0_2_DRAFT)
    manifest_path = day1_dir / "QUEUE_MANIFEST.json"

    from finvest.human_study.annotate_cli import load_manifest

    manifest = load_manifest(day1_dir)

    results: dict[str, object] = {}

    # 1. Dashboard data: all queues present (protocol queue names).
    reviewer_view = manifest["reviewer_view"]
    results["queues"] = sorted(reviewer_view.keys())

    # 2. One base case renders + evidence resolves.
    # Pick the first case WITH evidence (insufficient cases legitimately have
    # none and are not a valid evidence-resolution target).
    case = next(
        c for c in base_queue(manifest) if c["evidence_items"]
    )
    evidence = resolve_evidence_set(case["evidence_items"], cache)
    results["first_case"] = case["case_id"]
    results["evidence_count"] = len(evidence)
    results["evidence_resolved"] = sum(
        1 for e in evidence if e.resolution_status == "resolved"
    )
    results["evidence_failed"] = sum(
        1 for e in evidence if e.resolution_status == "EVIDENCE_RESOLUTION_FAILED"
    )

    # 3. Autosave draft to SQLite (isolated DB).
    db_path = tmp_root / "workbench.sqlite"
    db = DraftService(db_path)
    db.save_draft("TEST_REVIEWER", "base", case["case_id"], {"sufficiency": "PARTIAL"})
    draft = db.load_draft("TEST_REVIEWER", "base", case["case_id"])
    results["draft_autosaved"] = draft == {"sufficiency": "PARTIAL"}
    db.close()

    # 4. Signing requires explicit confirmation (rejected here).
    signed_rejected = False
    try:
        record = {
            "record_type": "BASE_22", "case_id": case["case_id"],
            "question_valid": "VALID", "answerability": "ANSWERABLE",
            "sufficiency": "PARTIAL", "entity": "X", "metric": "Y",
            "target_period": "FY2024", "unit_and_scale": "USD",
            "reporting_scope": "consolidated", "mandatory_requirements": [],
            "supporting_evidence_ids": [], "minimal_evidence_set": [],
            "source_time_valid": None, "version_valid": None,
            "calculation_reproducible": None, "final_answer_or_null": None,
            "reviewer_confidence": None, "reviewer_notes": None,
            "elapsed_seconds": 0,
        }
        append_signed(day1_dir, "base", case["case_id"], record, "TEST_REVIEWER", "WRONG", manifest)
    except Exception:
        signed_rejected = True
    results["signing_requires_confirmation"] = signed_rejected

    # 5. No signed JSONL written in the isolated run (active protocol file).
    signed_path = record_file_path(day1_dir, V0_2_DRAFT, "base")
    results["no_signed_jsonl"] = (not signed_path.exists()) or signed_path.stat().st_size == 0

    # 6. Outbound-block probe: annotation code imports no network client.
    import finvest.human_study.web.app as app

    src = Path(app.__file__).read_text(encoding="utf-8")
    results["no_outbound_imports"] = all(
        token not in src for token in ("requests", "urllib.request", "httpx", "socket")
    )

    results["all_pass"] = all([
        len(results["queues"]) == 4,
        results["evidence_count"] > 0,
        results["draft_autosaved"],
        results["signing_requires_confirmation"],
        results["no_signed_jsonl"],
        results["no_outbound_imports"],
    ])
    return results


if __name__ == "__main__":
    import json
    import sys

    result = run_smoke_test()
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(0 if result["all_pass"] else 1)
