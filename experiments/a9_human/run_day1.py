"""Day-1 human-validation pilot — one-command orchestration + annotation CLI.

Subcommands:
  freeze       build + freeze queues, hashes, empty human-record files
  verify       re-verify frozen hashes
  status       annotation status (counts, drafts, blind gate, violations)
  annotate     interactive annotation (strictly neutral, human-controlled)
  review-draft show one unsigned draft exactly as stored
  sign         sign a saved unsigned draft (typed confirmation required)
  correct      amend a signed record (creates an audit entry, never overwrites)
  reliability  descriptive intra-rater stats (base pass-1 vs blind pass-2)
  vista        run the gated VISTA pilot (INSUFFICIENT_DATA until labels sign)

Examples:
  python -m experiments.a9_human.run_day1 status
  python -m experiments.a9_human.run_day1 annotate base --reviewer-id ELIAN_PRIMARY --resume
  python -m experiments.a9_human.run_day1 annotate paired --reviewer-id ELIAN_PRIMARY
  python -m experiments.a9_human.run_day1 annotate interface --reviewer-id ELIAN_PRIMARY
  python -m experiments.a9_human.run_day1 annotate blind --reviewer-id ELIAN_PRIMARY
  python -m experiments.a9_human.run_day1 review-draft finvest-AAPL-fcff-2024
  python -m experiments.a9_human.run_day1 sign finvest-AAPL-fcff-2024 --reviewer-id ELIAN_PRIMARY
  python -m experiments.a9_human.run_day1 correct finvest-AAPL-fcff-2024 --queue base \
      --reviewer-id ELIAN_PRIMARY --reason "typo in reported value"
"""

from __future__ import annotations

import argparse
import json
import sys

from finvest.human_study.annotate_cli import (
    AnnotateOptions,
    CliError,
    DAY1_DIR,
    RealIO,
    load_manifest,
    load_records,
    record_file,
    run_annotate,
    run_correct,
    run_review_draft,
    run_sign,
    run_status,
)
from finvest.human_study.day1_pilot import (
    ROOT,
    compute_intra_rater,
    freeze_day1,
    run_vista_pilot,
    verify_frozen,
)

VISTA_OUTPUT = ROOT / "artifacts/results/VISTA_PILOT_V0_1.json"


def _out(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Preparation + analysis commands
# ---------------------------------------------------------------------------

def cmd_freeze(args: argparse.Namespace) -> int:
    manifest = freeze_day1()
    _out({
        "manifest_id": manifest["manifest_id"],
        "frozen_at": manifest["frozen_at"],
        "components": {k: v[:12] for k, v in manifest["components"].items()},
        "total_sha256": manifest["total_sha256"],
    })
    print(f"frozen artifacts written under {DAY1_DIR.relative_to(ROOT)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    _out(verify_frozen())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    manifest = load_manifest(DAY1_DIR)
    return run_status(manifest, RealIO(), day1_dir=DAY1_DIR)


def cmd_reliability(args: argparse.Namespace) -> int:
    manifest = load_manifest(DAY1_DIR)
    base = load_records(record_file(DAY1_DIR, "base"))
    blind = load_records(record_file(DAY1_DIR, "blind"))
    selection = manifest["sealed"]["blind_repeat_5_selection"]
    _out(compute_intra_rater(base, blind, selection))
    return 0


def cmd_vista(args: argparse.Namespace) -> int:
    _out(run_vista_pilot(DAY1_DIR, VISTA_OUTPUT))
    return 0


# ---------------------------------------------------------------------------
# Annotation commands
# ---------------------------------------------------------------------------

def cmd_annotate(args: argparse.Namespace) -> int:
    manifest = load_manifest(DAY1_DIR)
    opts = AnnotateOptions(
        reviewer_id=args.reviewer_id,
        resume=args.resume,
        limit=args.limit,
        case_id=args.case_id,
        start_at=args.start_at,
    )
    run_annotate(manifest, args.queue, opts, RealIO(), day1_dir=DAY1_DIR)
    return 0


def cmd_review_draft(args: argparse.Namespace) -> int:
    run_review_draft(DAY1_DIR, args.key, RealIO())
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    manifest = load_manifest(DAY1_DIR)
    return run_sign(manifest, DAY1_DIR, args.key, args.reviewer_id, RealIO())


def cmd_correct(args: argparse.Namespace) -> int:
    manifest = load_manifest(DAY1_DIR)
    return run_correct(
        manifest, DAY1_DIR, args.queue, args.key, args.reviewer_id,
        args.reason, RealIO(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.a9_human.run_day1",
        description="Day-1 single-researcher human-validation pilot.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("freeze", help="build + freeze queues (preparation only)")
    sub.add_parser("verify", help="re-verify frozen hashes")
    sub.add_parser("status", help="annotation status (counts, drafts, blind gate)")
    sub.add_parser("reliability", help="descriptive intra-rater stats (both passes)")

    p_annotate = sub.add_parser(
        "annotate",
        help="interactive annotation (strictly neutral, human-controlled)",
    )
    p_annotate.add_argument("queue", choices=["base", "paired", "interface", "blind"])
    p_annotate.add_argument("--reviewer-id", required=True,
                            help="signing identifier (e.g. ELIAN_PRIMARY)")
    p_annotate.add_argument("--resume", action="store_true",
                            help="skip already-signed cases")
    p_annotate.add_argument("--limit", type=int, help="max cases this run")
    p_annotate.add_argument("--case-id", help="annotate only this case/token/temp-id")
    p_annotate.add_argument("--start-at", help="start from this case/token/temp-id")

    p_review = sub.add_parser("review-draft", help="show one unsigned draft as stored")
    p_review.add_argument("key")

    p_sign = sub.add_parser("sign", help="sign a saved unsigned draft")
    p_sign.add_argument("key")
    p_sign.add_argument("--reviewer-id", required=True)

    p_correct = sub.add_parser("correct", help="amend a signed record (audit entry)")
    p_correct.add_argument("key")
    p_correct.add_argument("--queue", choices=["base", "paired", "interface", "blind"],
                           default="base")
    p_correct.add_argument("--reviewer-id", required=True)
    p_correct.add_argument("--reason", required=True)

    p_vista = sub.add_parser("vista", help="gated VISTA pilot run")
    return parser


COMMANDS = {
    "freeze": cmd_freeze,
    "verify": cmd_verify,
    "status": cmd_status,
    "reliability": cmd_reliability,
    "vista": cmd_vista,
    "annotate": cmd_annotate,
    "review-draft": cmd_review_draft,
    "sign": cmd_sign,
    "correct": cmd_correct,
}


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except CliError as exc:
        print(f"error: {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("interrupted — unsigned drafts are preserved in "
              "human_review/day1/drafts/")
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
