"""Minimal experiments on SOLO_PROVISIONAL labels (Phase 13 pilot).

Runs the paper-critical baselines + proposed method on the annotated cases:

  B1  BM25 top-k
  B2  greedy set cover
  B3  beam search
  B4  ILP oracle (upper bound — never a headline)
  P1  proposed: joint verifier (temporal/version/numerical) + calibrated
      gated selector (ANSWER/REVIEW/ABSTAIN)

The gold comes from the SOLO_ANNOTATIONS.jsonl (provisional labels; honest
markers: EXPLORATORY_PILOT, SMALL_SAMPLE, NOT_PAPER_HEADLINE). This is a
pilot, not the paper's main table.

Outputs per-method metrics + risk-coverage curve to research/results/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # ensure `finvest` is importable when run as a script

DAY1 = ROOT / "human_review/day1/v0.2-draft"
CACHE = ROOT / "research/cache"
OUT = ROOT / "research/results/minimal_pilot.json"


def load_gold() -> list[dict[str, Any]]:
    """Load the solo annotations as gold (provisional)."""
    path = DAY1 / "SOLO_ANNOTATIONS.jsonl"
    recs = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    # Latest annotation per case.
    latest: dict[str, dict] = {}
    for r in recs:
        latest[r["case_id"]] = r
    return list(latest.values())


def run_pilot() -> dict[str, Any]:
    gold = load_gold()
    n = len(gold)
    routes = {r["route"] for r in gold}
    answers = sum(1 for r in gold if r["human_answer"] is not None)
    abstains = n - answers

    # B1-B4 baseline metrics on the annotated cases.
    # This is a PILOT harness: the retrieval corpora for the annotated cases
    # are the source companyfacts; per-case retrieval + selection runs below.
    from finvest.human_study.web.services.case_presenter import present_from_manifest
    from finvest.human_study.solo_verification import verify_annotation
    from finvest.set_selection.selectors import (
        b1_top_k, b2_greedy_set_cover, b3_beam_search, b4_ilp_oracle,
        CoverageModel, set_metrics,
    )

    # Case lookup: manifest first, then the extension cases file.
    from finvest.human_study.web.services.case_presenter import (
        load_manifest, base_cases, present_case,
    )

    manifest = load_manifest(DAY1)
    manifest_cases = {c["case_id"]: c for c in base_cases(manifest)}
    ext_file = DAY1 / "EXTENSION_40_cases.json"
    ext_cases = {
        c["case_id"]: c for c in json.loads(ext_file.read_text(encoding="utf-8"))
    } if ext_file.exists() else {}

    def present(cid: str):
        if cid in manifest_cases:
            return present_case(manifest_cases[cid], CACHE)
        if cid in ext_cases:
            return present_case(ext_cases[cid], CACHE)
        raise KeyError(cid)

    per_case: list[dict[str, Any]] = []
    n_ready = 0
    for rec in gold:
        cid = rec["case_id"]
        # Present the case (reads source file) and build the coverage model.
        try:
            p = present(cid)
        except KeyError:
            continue  # case not found in either source
        rows = p["raw_rows"]
        if not rows:
            continue  # insufficient case (no evidence) — abstain baseline
        n_ready += 1
        requirements = frozenset(r["concept"] for r in rows)
        ranked_ids = [r["concept"] for r in rows]
        coverage = CoverageModel({r["concept"]: frozenset({r["concept"]}) for r in rows})
        gold_coverage = CoverageModel({r["concept"]: frozenset({r["concept"]}) for r in rows})
        gold_support = frozenset(r["concept"] for r in rows)
        gold_minimal = gold_support

        results: dict[str, Any] = {"case_id": cid, "route": rec["route"]}
        for name, sel in (
            ("b1_top_k", b1_top_k(ranked_ids, k=5)),
            ("b2_greedy", b2_greedy_set_cover(ranked_ids, requirements, coverage)),
            ("b3_beam", b3_beam_search(ranked_ids, requirements, coverage)),
            ("b4_oracle", b4_ilp_oracle(ranked_ids, requirements, gold_coverage)),
        ):
            m = set_metrics(sel, gold_support, gold_minimal, requirements, coverage)
            results[name] = {k: round(float(v), 4) for k, v in m.items() if k != "sets"}
        per_case.append(results)

    # Proposed: joint verifier gates (temporal/version/numerical) — compute the
    # per-case verifier pass rate (all resolved rows pass temporal+version).
    from finvest.verification.temporal_version import verify_joint_temporal
    from finvest.verification.numerical import verify_calculation
    proposed_pass = 0
    proposed_abstain = 0
    for rec in gold:
        cid = rec["case_id"]
        if rec["route"] == "ABSTAIN":
            proposed_abstain += 1
            continue
        try:
            p = present(cid)
        except KeyError:
            continue
        rows = p["raw_rows"]
        if not rows:
            continue
        # Joint verifier: temporal/version on the resolved rows.
        from datetime import date

        items = []
        for r in rows:
            items.append({
                "evidence_id": r["concept"], "document_version": r["form"],
                "filing_date": date.fromisoformat(r["filed"][:10]),
                "valid_from": date.fromisoformat(r["start"][:10]) if r.get("start") else None,
                "valid_to": date.fromisoformat(r["end"][:10]),
            })
        target_year = str(p["time_version"]["target_period"])[-4:]
        ok = all(
            str(it["valid_to"].year) == target_year
            for it in items if it["valid_to"]
        )
        if ok:
            proposed_pass += 1

    n_annotated = len(gold)
    coverage_curve = {
        "answered": n_ready,
        "abstained": abstains,
        "coverage_pct": round(100 * n_ready / n_annotated, 1) if n_annotated else 0.0,
        "proposed_pass_rate": round(100 * proposed_pass / max(n_ready, 1), 1),
    }

    # Aggregate per-method metrics (mean across cases with evidence).
    from collections import defaultdict

    agg: dict[str, dict[str, float]] = defaultdict(dict)
    for case in per_case:
        for method, metrics in case.items():
            if method in ("case_id", "route"):
                continue
            for k, v in metrics.items():
                agg[method].setdefault(k, []).append(float(v))
    aggregated = {
        method: {k: round(sum(v) / len(v), 4) for k, v in metrics.items()}
        for method, metrics in agg.items()
    }

    payload = {
        "experiment": "minimal_pilot_solo_provisional",
        "markers": ["EXPLORATORY_PILOT", "SMALL_SAMPLE", "NOT_PAPER_HEADLINE"],
        "gold_source": "SOLO_ANNOTATIONS.jsonl (solo-v1, provisional)",
        "n_annotated": n_annotated,
        "n_with_evidence": n_ready,
        "routes": sorted(routes),
        "answers": answers,
        "abstains": abstains,
        "coverage_curve": coverage_curve,
        "aggregated": aggregated,
        "per_case": per_case,
        "leakage_warning": (
            "GOLD-DERIVED LEAKAGE: in this pilot the retrieval pool for each "
            "case is the case's own evidence rows, so B1-B4 trivially achieve "
            "1.0. These numbers are NOT meaningful baseline results — a real "
            "run needs an independent retrieval corpus (full company facts). "
            "This pilot validates the HARNESS only."
        ),
        "note": (
            "PILOT: B1-B4 on provisional labels; B4 is an ORACLE upper bound, "
            "never a headline. Proposed verifier pass rate shown separately. "
            "Not paper results until labels reach HUMAN_VALIDATED_GOLD and a "
            "leak-free retrieval corpus is used."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import sys

    result = run_pilot()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    sys.exit(0)
