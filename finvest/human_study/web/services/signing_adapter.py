"""Signing adapter — connects the web flow to the AUTHORITATIVE signing logic.

This is a thin adapter over the existing annotate_cli signing path. It does NOT
reimplement signing; it reuses record_problems (schema/evidence validation) and
_append_record (the only writer of signed JSONL). The web UI can never write
signed JSONL directly.

Explicit typed confirmation is preserved: the caller supplies the confirmation
string; signing only happens when it equals ``SIGN <key>``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from finvest.human_study import annotate_cli as cli


def record_problems_for(
    day1_dir: Path, queue: str, key: str, record: dict, manifest: dict
) -> list[str]:
    """Schema/existence problems (CLI-authoritative). Empty = valid."""
    return cli.record_problems(queue, key, record, manifest)


def append_signed(
    day1_dir: Path,
    queue: str,
    key: str,
    record: dict,
    reviewer_id: str,
    confirmation: str,
    manifest: dict,
    now: datetime | None = None,
) -> dict:
    """Append a signed record ONLY when confirmation == SIGN <key>."""
    if confirmation.strip() != f"SIGN {key}":
        raise cli.CliError("explicit typed confirmation required: SIGN <key>")
    now = now or datetime.now(timezone.utc)
    record = dict(record)
    record["signed"] = True
    record["signed_by"] = reviewer_id
    record["timestamp"] = now.isoformat(timespec="seconds")
    problems = cli.record_problems(queue, key, record, manifest)
    if problems:
        raise cli.CliError("record invalid, nothing appended: " + "; ".join(problems))
    cli._append_record(day1_dir, queue, record)
    return record


def correction_audit(
    day1_dir: Path,
    key: str,
    queue: str,
    old: dict,
    new: dict,
    reason: str,
    reviewer_id: str,
    now: datetime | None = None,
) -> None:
    """Append a correction audit entry (immutable history)."""
    cli._append_audit(day1_dir, key, queue, old, new, reason, reviewer_id, now)


def is_signed(day1_dir: Path, queue: str, key: str) -> bool:
    return key in cli.signed_index(cli.record_file(day1_dir, queue), queue)


def latest_signed(day1_dir: Path, queue: str, key: str) -> dict | None:
    return cli.signed_index(cli.record_file(day1_dir, queue), queue).get(key)
