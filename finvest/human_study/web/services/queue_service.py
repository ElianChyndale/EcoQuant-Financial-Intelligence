"""Workbench queue service — wraps the authoritative annotate_cli queue logic.

No annotation logic is reimplemented here; these functions are thin adapters
over the frozen manifest and the existing CLI's view projections, so the web UI
and CLI share one source of truth.
"""

from __future__ import annotations

from pathlib import Path

from finvest.human_study import annotate_cli as cli


def queue_views(day1_dir: Path, queue: str, manifest: dict) -> list[dict]:
    """Display-safe frozen views for a queue (CLI-authoritative projection)."""
    return cli._views(manifest, queue)


def queue_keys(day1_dir: Path, queue: str, manifest: dict) -> list[str]:
    return [cli._key_of_view(queue, v) for v in cli._views(manifest, queue)]


def signed_keys(day1_dir: Path, queue: str) -> list[str]:
    index, _ = cli.index_records(
        cli.load_records(cli.record_file(day1_dir, queue)),
        lambda r, q=queue: cli._key_of_record(q, r),
    )
    return sorted(index)


def queue_record_types() -> dict[str, str]:
    return dict(cli.QUEUE_RECORD_TYPES)


def key_field(queue: str) -> str:
    return cli.QUEUE_KEY_FIELDS[queue]


def valid_evidence_ids_for(day1_dir: Path, queue: str, key: str, manifest: dict) -> frozenset[str]:
    return cli._valid_evidence_ids_for_record(queue, key, manifest)
