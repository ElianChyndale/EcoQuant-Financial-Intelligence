"""Minimal experiments on SOLO_PROVISIONAL labels (Phase 13 pilot).

This pilot validates the HARNESS, not the methods. It runs on the annotated
cases and is HONEST about its own gold-derived leakage: the per-case retrieval
pool is the case's own resolved evidence rows, so baseline numbers are not
meaningful retrieval results. A real two-stage experiment runs in
experiments/a11_retrieval/ against a leak-free corpus.

Layers reported:
  retrieval      R1-R4  — DEFERRED to a11 (this pilot's pool is leaked)
  set_selection  S1-S4  — top-k / greedy / beam / ILP-oracle on the case rows
  verification   V1-V3  — joint temporal/version, numerical, combined

Honest markers: EXPLORATORY_PILOT, SMALL_SAMPLE, NOT_PAPER_HEADLINE.
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

# Report-layer labels for the set-selection selectors. The selector function
# names in finvest/set_selection/selectors.py are unchanged (tests assert them);
# only the reporting here relabels B1-B4 as S1-S4 to stop calling set selectors
# "retrieval baselines".
S_LABELS = {
    "b1_top_k": "S1_top_k",
    "b2_greedy": "S2_greedy_set_cover",
    "b3_beam": "S3_beam_search",
    "b4_oracle": "S4_ilp_oracle",
}


def load_gold() -> list[dict[str, Any]]:
    """Load the solo annotations as gold (provisional)."""
    path = DAY1 / "SOLO_ANNOTATIONS.jsonl"
    recs = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    # Latest annotation per case.
    latest: dict[str, dict] = {}
    for r in recs:
        latest[r["case_id"]] = r
    return list(latest.values())


def _evidence_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build EvidenceItem-shaped dicts from raw evidence rows.

    Mirrors the joint temporal verifier's input shape: source-time, valid-time,
    period, and version fields are all populated from the raw row.
    """
    from datetime import date

    items = []
    for r in rows:
        items.append({
            "evidence_id": r["concept"],
            "document_id": r.get("source_file", ""),
            "document_version": r["form"],
            "filing_date": date.fromisoformat(r["filed"][:10]) if r.get("filed") else None,
            "valid_from": date.fromisoformat(r["start"][:10]) if r.get("start") else None,
            "valid_to": date.fromisoformat(r["end"][:10]) if r.get("end") else None,
            "unit": r.get("unit"),
            "concept": r.get("concept"),
            "text_span": _render_fact(r),
        })
    return items


def _render_fact(r: dict[str, Any]) -> str:
    """Render a raw row into a searchable evidence text span."""
    parts = [str(r.get("concept") or "")]
    if r.get("val") is not None:
        parts.append(str(r["val"]))
    if r.get("unit"):
        parts.append(str(r["unit"]))
    if r.get("start"):
        parts.append(str(r["start"]))
    if r.get("end"):
        parts.append(str(r["end"]))
    if r.get("filed"):
        parts.append(str(r["filed"]))
    if r.get("form"):
        parts.append(str(r["form"]))
    if r.get("accn"):
        parts.append(str(r["accn"]))
    return " ".join(parts)


def _verification_layer(
    rows: list[dict[str, Any]],
    *,
    source_cutoff: str | None,
    target_fiscal_year: str | None,
    target_period_end: str | None,
    calculation_program: dict[str, Any] | None,
    expected_value: float | None,
) -> dict[str, Any]:
    """Run the REAL joint temporal/version and numerical verifiers per case.

    Returns per-check verdicts plus a combined joint verdict. This is the fix
    for the old pilot, which only compared valid_to.year to the target year.
    """
    from datetime import datetime

    from finvest.benchmark.schemas import EvidenceItem, VersionRelation
    from finvest.verification.temporal_version import verify_joint_temporal
    from finvest.verification.numerical import NumericalVerification

    items = [
        EvidenceItem(
            evidence_id=it["evidence_id"],
            document_id=it["document_id"],
            document_version=it["document_version"],
            filing_date=it["filing_date"] or datetime(1970, 1, 1).date(),
            valid_from=it["valid_from"],
            valid_to=it["valid_to"],
            unit=it["unit"],
            concept=it["concept"],
            text_span=it["text_span"],
        )
        for it in _evidence_items(rows)
    ]
    if not items:
        return {"verification_state": "INSUFFICIENT_EVIDENCE", "checks": {}, "valid": False}

    cutoff = None
    if source_cutoff:
        cutoff = datetime.fromisoformat(str(source_cutoff).replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=datetime.now().astimezone().tzinfo)
    target_end = None
    if target_period_end:
        from datetime import date as _date
        target_end = _date.fromisoformat(str(target_period_end)[:10])

    relations = tuple(VersionRelation(**rel) for rel in [])  # pilot: no version relations loaded
    temporal = verify_joint_temporal(
        tuple(items),
        source_cutoff=cutoff or datetime(1970, 1, 1),
        target_end=target_end,
        target_fiscal_year=target_fiscal_year,
        version_relations=relations,
    )

    # V2 numerical (derived cases only; extractive answers have no operation).
    # Feed the actual fact values in program-input order. The raw rows are the
    # resolved evidence for the case; their order matches the calculation
    # program's input order (OCF, CapEx). Matching by concept name is brittle
    # (inputs use display names like "OperatingCashFlow", rows use XBRL names),
    # so we align by position through the program's input count.
    numerical = None
    if calculation_program and calculation_program.get("operation"):
        from ecoquant.research.table_eval.calculate import calculate as _calc

        _op = calculation_program["operation"]
        _n_inputs = len(calculation_program.get("inputs") or [])
        _values: list[float] = []
        for r in rows[: _n_inputs if _n_inputs else len(rows)]:
            if r.get("val") is not None:
                try:
                    _values.append(float(r["val"]))
                except (TypeError, ValueError):
                    pass
        if _values:
            # The executor (ecoquant calculate) supports the six GRI-QA
            # functions, not the case generator's op names. Map subtract
            # (OCF - |CapEx|; raw rows are OCF then CapEx, CapEx value is
            # positive in the source) to sum of [ocf, -capex].
            _exec_op = _op
            if _op == "subtract" and len(_values) >= 2:
                _values = [_values[0], -abs(_values[1])]
                _exec_op = "sum"
            try:
                _result = _calc(_exec_op, _values)
                if expected_value is not None:
                    _ok = abs(_result - expected_value) / max(1.0, abs(expected_value)) <= 0.01
                    numerical = NumericalVerification(
                        True, _result, "SUPPORTED" if _ok else "REVIEW_REQUIRED",
                        "matches gold within tolerance" if _ok else "mismatch vs gold",
                    )
                else:
                    numerical = NumericalVerification(True, _result, "SUPPORTED", "executed, no gold to check")
            except (ValueError, ZeroDivisionError) as _exc:
                numerical = NumericalVerification(False, None, "REVIEW_REQUIRED", f"calc failed: {_exc}")
        else:
            numerical = NumericalVerification(False, None, "INSUFFICIENT_EVIDENCE", "no numeric evidence for operation inputs")

    # Unit/scale consistency: all rows must share one unit.
    units = {r.get("unit") for r in rows if r.get("unit")}
    unit_scale_consistent = len(units) <= 1

    temporal_ok = temporal.valid
    numerical_ok = numerical is None or numerical.verification_state == "SUPPORTED"
    v3_joint = temporal_ok and numerical_ok and unit_scale_consistent

    return {
        "valid": bool(v3_joint),
        "verification_state": "SUPPORTED" if v3_joint else "REVIEW_REQUIRED",
        "checks": {
            "v1_temporal": {
                "valid": temporal.valid,
                "future_information_rate": round(temporal.future_information_rate, 4),
                "expired_evidence_rate": round(temporal.expired_evidence_rate, 4),
                "wrong_period_rate": round(temporal.wrong_period_rate, 4),
                "superseded_rate": round(temporal.superseded_rate, 4),
                "violations": list(temporal.violations[:5]),
            },
            "v2_numerical": {
                "present": numerical is not None,
                "verification_state": numerical.verification_state if numerical else None,
                "result": numerical.result if numerical else None,
            },
            "unit_scale_consistent": unit_scale_consistent,
            "units": sorted(units),
        },
    }


def run_pilot() -> dict[str, Any]:
    gold = load_gold()
    n = len(gold)
    routes = {r["route"] for r in gold}
    answers = sum(1 for r in gold if r["human_answer"] is not None)
    abstains = n - answers

    from finvest.human_study.web.services.case_presenter import (
        load_manifest, base_cases, present_case,
    )
    from finvest.set_selection.selectors import (
        b1_top_k, b2_greedy_set_cover, b3_beam_search, b4_ilp_oracle,
        CoverageModel, set_metrics,
    )

    manifest = load_manifest(DAY1)
    manifest_cases = {c["case_id"]: c for c in base_cases(manifest)}
    ext_file = DAY1 / "EXTENSION_40_cases.json"
    ext_cases = {
        c["case_id"]: c for c in json.loads(ext_file.read_text(encoding="utf-8"))
    } if ext_file.exists() else {}
    sealed = {**manifest_cases, **ext_cases}

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
        try:
            p = present(cid)
        except KeyError:
            continue  # case not found in either source
        rows = p["raw_rows"]
        if not rows:
            continue  # insufficient case (no evidence) — abstain baseline
        n_ready += 1

        case = sealed.get(cid, {})
        requirements = frozenset(r["concept"] for r in rows)
        ranked_ids = [r["concept"] for r in rows]
        coverage = CoverageModel({r["concept"]: frozenset({r["concept"]}) for r in rows})
        gold_coverage = CoverageModel({r["concept"]: frozenset({r["concept"]}) for r in rows})
        gold_support = frozenset(r["concept"] for r in rows)
        gold_minimal = gold_support

        result: dict[str, Any] = {"case_id": cid, "route": rec["route"]}

        # --- set-selection layer (S1-S4) — relabeled in reporting ---
        set_results: dict[str, Any] = {}
        for name, sel in (
            ("b1_top_k", b1_top_k(ranked_ids, k=5)),
            ("b2_greedy", b2_greedy_set_cover(ranked_ids, requirements, coverage)),
            ("b3_beam", b3_beam_search(ranked_ids, requirements, coverage)),
            ("b4_oracle", b4_ilp_oracle(ranked_ids, requirements, gold_coverage)),
        ):
            m = set_metrics(sel, gold_support, gold_minimal, requirements, coverage)
            s_name = S_LABELS[name]
            set_results[s_name] = {k: round(float(v), 4) for k, v in m.items() if k != "sets"}
            if name == "b4_oracle":
                set_results[s_name]["is_oracle"] = True
        result["set_selection"] = set_results

        # --- verification layer (V1-V3) — actually calls the joint verifiers ---
        gold_answer = case.get("gold_answer") or {}
        expected_value = gold_answer.get("value")
        result["verification"] = _verification_layer(
            rows,
            source_cutoff=case.get("source_cutoff") or p.get("time_version", {}).get("source_cutoff"),
            target_fiscal_year=case.get("target_fiscal_year") or p.get("time_version", {}).get("target_period"),
            target_period_end=case.get("target_period_end"),
            calculation_program=case.get("calculation_program"),
            expected_value=expected_value,
        )

        # --- retrieval layer — honest: this pilot's pool is the case's own rows ---
        result["retrieval"] = {
            "pool": "case_own_raw_rows (GOLD-DERIVED, LEAKED)",
            "retrieval_metrics": "deferred_to_a11",
            "note": "Real R1-R4 retrieval runs in experiments/a11_retrieval/ against a leak-free corpus.",
        }
        per_case.append(result)

    # --- aggregate set-selection metrics (mean across cases with evidence) ---
    from collections import defaultdict

    agg: dict[str, dict[str, float]] = defaultdict(dict)
    for case in per_case:
        for method, metrics in case.get("set_selection", {}).items():
            for k, v in metrics.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    agg[method].setdefault(k, []).append(float(v))
    aggregated = {
        method: {k: round(sum(v) / len(v), 4) for k, v in metrics.items()}
        for method, metrics in agg.items()
    }

    # --- aggregate verification checks ---
    v_check_counts: dict[str, list[bool]] = defaultdict(list)
    v_state_counts: dict[str, int] = defaultdict(int)
    for case in per_case:
        v = case.get("verification", {})
        v_state_counts[v.get("verification_state", "UNKNOWN")] += 1
        checks = v.get("checks", {})
        v1 = checks.get("v1_temporal", {})
        if "valid" in v1:
            v_check_counts["v1_temporal"].append(bool(v1["valid"]))
        if "v1_temporal" in checks:
            v_check_counts["filing_cutoff"].append(bool(checks["v1_temporal"]["future_information_rate"] == 0))
            v_check_counts["target_period_match"].append(bool(checks["v1_temporal"]["wrong_period_rate"] == 0))
            v_check_counts["version_consistency"].append(bool(checks["v1_temporal"]["superseded_rate"] == 0))
        v2 = checks.get("v2_numerical", {})
        if v2.get("present"):
            v_check_counts["numerical_calculation"].append(v2.get("verification_state") == "SUPPORTED")
        if "unit_scale_consistent" in checks:
            v_check_counts["unit_scale"].append(bool(checks["unit_scale_consistent"]))
        v_check_counts["joint"].append(bool(v.get("valid", False)))

    def _rate(key: str) -> float:
        items = v_check_counts.get(key, [])
        return round(100 * sum(items) / len(items), 1) if items else 0.0

    n_annotated = len(gold)
    coverage_curve = {
        "n_presentable_cases": n_ready,
        "abstained": abstains,
        "evidence_availability_rate": round(100 * n_ready / n_annotated, 1) if n_annotated else 0.0,
        "target_period_match_rate": _rate("target_period_match"),
        "verification_pass_rate": _rate("joint"),
    }

    verification_rates = {
        "joint_verifier_invoked": True,  # real joint temporal/version + numerical verifiers now run
        "filing_cutoff_pass_rate": _rate("filing_cutoff"),
        "temporal_verifier_pass": _rate("v1_temporal"),
        "version_verifier_pass": _rate("version_consistency"),
        "numerical_verifier_pass": _rate("numerical_calculation"),
        "unit_scale_consistency_rate": _rate("unit_scale"),
        "joint_verifier_pass": _rate("joint"),
    }

    payload = {
        "experiment": "A10_HARNESS_INTEGRITY_PILOT",
        "schema_version": "minimal_pilot.v2",
        "markers": ["EXPLORATORY_PILOT", "SMALL_SAMPLE", "NOT_PAPER_HEADLINE"],
        "gold_source": "SOLO_ANNOTATIONS.jsonl (solo-v1, provisional)",
        "n_annotated": n_annotated,
        "n_with_evidence": n_ready,
        "routes": sorted(routes),
        "answers": answers,
        "abstains": abstains,
        "coverage_curve": coverage_curve,
        "verification_rates": verification_rates,
        "layers": {
            "retrieval": "deferred_to_a11 (leak-free corpus)",
            "set_selection": sorted(S_LABELS.values()),
            "verification": ["V1_temporal", "V2_numerical", "V3_joint"],
        },
        "aggregated": aggregated,
        "verification_state_counts": dict(v_state_counts),
        "per_case": per_case,
        "leakage_warning": (
            "GOLD-DERIVED LEAKAGE: in this pilot the retrieval pool for each "
            "case is the case's own evidence rows, so the set-selection "
            "selectors trivially achieve 1.0. These numbers are NOT meaningful "
            "baseline results — a real run needs an independent retrieval "
            "corpus (full company facts). This pilot validates the HARNESS only."
        ),
        "note": (
            "PILOT: S1-S4 on provisional labels; S4 is an ORACLE upper bound, "
            "never a headline. V1-V3 now run the real joint temporal/version "
            "and numerical verifiers; verification_pass_rate reflects those, "
            "not a year-equality check. Not paper results until labels reach "
            "HUMAN_VALIDATED_GOLD and a leak-free retrieval corpus is used."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run_pilot()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    sys.exit(0)
