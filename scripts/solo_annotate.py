"""Conversational solo-provisional annotation entry (Phase 13).

Usage (chat-based; the assistant drives it):
    python scripts/solo_annotate.py present <case_id>        # Stage 0-1: evidence package + gate
    python scripts/solo_annotate.py verify <case_id> <answer> [--route R] [--flags F1,F2]
    python scripts/solo_annotate.py status [<case_id>]       # list statuses

The presentation reads the SOURCE FILE from disk at call time (never from
memory), shows raw rows verbatim + human-readable table + calculation inputs,
and hides machine answers until AFTER the human judgement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY1 = ROOT / "human_review" / "day1" / "v0.2-draft"
CACHE = ROOT / "research" / "cache"
RECORDS = DAY1 / "SOLO_ANNOTATIONS.jsonl"

sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("present", help="Present the evidence package (reads source file).")
    p.add_argument("case_id")

    v = sub.add_parser("verify", help="Run machine verification after the human answer.")
    v.add_argument("case_id")
    v.add_argument("answer")
    v.add_argument("--route", choices=("ANSWER", "REVIEW", "ABSTAIN"), default="ANSWER")
    v.add_argument("--confidence", choices=("HIGH", "MEDIUM", "LOW"), default="MEDIUM")
    v.add_argument("--q1", choices=("CLEAR", "AMBIGUOUS", "INVALID"), default="CLEAR")
    v.add_argument("--q2", choices=("ENOUGH", "PARTLY_ENOUGH", "CONFLICTING", "NOT_ENOUGH"), default="ENOUGH")
    v.add_argument("--flags", default="NO_ISSUE", help="comma-separated issue flags")
    v.add_argument("--rationale", default="")

    s = sub.add_parser("status")
    s.add_argument("case_id", nargs="?", default=None)

    args = parser.parse_args()

    from finvest.human_study.web.services.case_presenter import (
        load_manifest, base_cases, present_case_markdown,
    )

    _manifest = load_manifest(DAY1)
    _cases = {c["case_id"]: c for c in base_cases(_manifest)}
    from finvest.human_study.solo_records import (
        SoloAnnotation, append_annotation, derive_labels, latest_annotation, load_annotations,
    )
    from finvest.human_study.solo_verification import verify_annotation, render_diff_report

    if args.cmd == "present":
        if args.case_id not in _cases:
            print(f"case {args.case_id} not found in manifest", file=sys.stderr)
            return 1
        md = present_case_markdown(_cases[args.case_id], CACHE)
        print(md)
        return 0

    if args.cmd == "status":
        if args.case_id:
            rec = latest_annotation(RECORDS, args.case_id)
            print(rec if rec else f"{args.case_id}: no annotation yet")
        else:
            by_case: dict[str, list] = {}
            for rec in load_annotations(RECORDS):
                by_case.setdefault(rec["case_id"], []).append(rec)
            for cid, recs in sorted(by_case.items()):
                last = recs[-1]
                print(f"{cid:<70} {last['status']:<28} route={last['route']} conf={last['confidence']}")
        return 0

    if args.cmd == "verify":
        from finvest.human_study.web.services.case_presenter import present_case
        manifest = load_manifest(DAY1)
        cases = {c["case_id"]: c for c in base_cases(manifest)}
        if args.case_id not in cases:
            print(f"case {args.case_id} not found", file=sys.stderr)
            return 1
        presented = present_case(cases[args.case_id], CACHE)
        raw_rows = presented["raw_rows"]

        # Machine verification AFTER the human answer (Stage 3).
        displayed = {r["concept"]: r["val"] for r in raw_rows}
        result = verify_annotation(
            raw_rows=raw_rows,
            human_answer=args.answer,
            human_route=args.route,
            source_cutoff=str(presented["time_version"]["source_cutoff"] or "") or None,
            target_period_end=str(presented["time_version"]["target_period"] or ""),
            displayed_values=displayed,
        )
        print(render_diff_report(result))

        # Build the append-only record (raw human choices + derived labels).
        flags = tuple(f.strip() for f in args.flags.split(",") if f.strip())
        derived = derive_labels(args.q1, args.q2, issue_flags=flags, route=args.route,
                                calc_mismatch=result.calc_match is False)
        status = "SOLO_PROVISIONAL" if derived["route"] != "REVIEW" else "NEEDS_EXTERNAL_REVIEW"

        # evidence_package_hash: the FULL frozen package hash (Phase 1.5), so a
        # change to any display/evidence field is visible. Fall back to the
        # legacy source-row hash only when the package cannot be built.
        from finvest.human_study.web.services.package_freeze import package_hash_for_case

        try:
            pkg_hash = package_hash_for_case(cases[args.case_id], CACHE)
        except Exception:
            pkg_hash = ""
        if not pkg_hash and presented["raw_rows"]:
            pkg_hash = presented["raw_rows"][0].get("source_hash", "")[:16] or ""

        ann = SoloAnnotation(
            case_id=args.case_id,
            evidence_package_version="1.0",
            evidence_package_hash=pkg_hash,
            annotation_protocol_version="solo-v1",
            reviewer_id="ELIAN_PRIMARY",
            annotation_round=1,
            question_clarity=args.q1,
            evidence_judgement=args.q2,
            selected_evidence_ids=tuple(r["concept"] for r in raw_rows),
            human_inputs={r["concept"]: r["val"] for r in raw_rows},
            human_answer=args.answer,
            issue_flags=flags,
            route=derived["route"],
            confidence=args.confidence,
            rationale=args.rationale,
            duration_seconds=0,
            derived=derived,
            status=status,
        )
        append_annotation(RECORDS, ann)
        print(f"\nSaved SOLO record for {args.case_id} -> status={status}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
