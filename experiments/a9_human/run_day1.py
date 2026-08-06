"""Day-1 human-validation pilot — one-command orchestration.

Subcommands:
  freeze       build + freeze queues, hashes, empty human-record files
  verify       re-verify frozen hashes
  reliability  compute descriptive intra-rater stats (requires both passes)
  vista        run the gated VISTA pilot (INSUFFICIENT_DATA until labels sign)

Example:
  python -m experiments.a9_human.run_day1 freeze
  python -m experiments.a9_human.run_day1 verify
  python -m experiments.a9_human.run_day1 vista
"""

from __future__ import annotations

import json
import sys

from finvest.human_study.day1_pilot import (
    DAY1_DIR,
    ROOT,
    compute_intra_rater,
    freeze_day1,
    run_vista_pilot,
    verify_frozen,
)

VISTA_OUTPUT = ROOT / "artifacts/results/VISTA_PILOT_V0_1.json"


def _load_records(name: str) -> list[dict[str, object]]:
    path = DAY1_DIR / name
    records: list[dict[str, object]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def cmd_freeze() -> int:
    manifest = freeze_day1()
    summary = {
        "manifest_id": manifest["manifest_id"],
        "frozen_at": manifest["frozen_at"],
        "components": {k: v[:12] for k, v in manifest["components"].items()},
        "total_sha256": manifest["total_sha256"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"frozen artifacts written under {DAY1_DIR.relative_to(ROOT)}")
    return 0


def cmd_verify() -> int:
    result = verify_frozen()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 1


def cmd_reliability() -> int:
    blind = _load_records("BLIND_REPEAT_5.jsonl")
    result = compute_intra_rater([dict(r) for r in blind])
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def cmd_vista() -> int:
    payload = run_vista_pilot(DAY1_DIR, VISTA_OUTPUT)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


COMMANDS = {
    "freeze": cmd_freeze,
    "verify": cmd_verify,
    "reliability": cmd_reliability,
    "vista": cmd_vista,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 1
    return COMMANDS[argv[0]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
