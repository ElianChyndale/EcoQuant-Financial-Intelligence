"""Workbench queue service — protocol-aware adapters over the frozen manifest.

The CLI's view projections are frozen to the v0.1 protocol, so the web layer
resolves the manifest's protocol and reads the protocol-specific sealed /
reviewer keys directly. Display projection (project_case) is shared with the
CLI; queue identity and record files come from the ProtocolConfig.
"""

from __future__ import annotations

from pathlib import Path

from finvest.human_study import annotate_cli as cli
from finvest.human_study.web.services.protocol_web import (
    LOGICAL_QUEUES,
    protocol_for_manifest,
    queue_name,
    record_file_path,
    reviewer_key,
    sealed_blind_key,
    sealed_interface_key,
    sealed_key,
    sealed_token_map_key,
)


def _cases_by_id(manifest: dict) -> dict[str, dict]:
    """case_id -> sealed case for the manifest's base queue."""
    return {c["case_id"]: c for c in manifest["sealed"][sealed_key(protocol_for_manifest(manifest), "base")]}


def _project(queue: str, manifest: dict, row: dict) -> dict:
    """Display-safe projection of one reviewer row (CLI-shared logic)."""
    if queue in ("base", "blind"):
        return cli.project_case(_cases_by_id(manifest)[row["case_id"]])
    return dict(row)


def queue_views(day1_dir: Path, queue: str, manifest: dict) -> list[dict]:
    """Display-safe frozen views for a queue (protocol-aware)."""
    proto = protocol_for_manifest(manifest)
    rkey = reviewer_key(proto, queue)
    if queue == "base":
        return [
            _project(queue, manifest, row)
            for row in manifest["reviewer_view"][rkey]
        ]
    if queue == "blind":
        selection = {
            row["temp_id"]: row["case_id"]
            for row in manifest["sealed"][sealed_blind_key(proto)]
        }
        return [
            {"temp_id": row["temp_id"], **_project("blind", manifest, {
                "case_id": selection[row["temp_id"]]})}
            for row in manifest["reviewer_view"][rkey]
        ]
    if queue == "interface":
        cases = {c["case_id"]: c for c in manifest["sealed"][sealed_key(proto, "base")]}
        views = []
        for case in manifest["sealed"][sealed_interface_key(proto)]:
            view: dict = {
                "case_id": case["case_id"],
                "base_question_id": case["base_question_id"],
                "display_condition": case["display_condition"],
                "question": cases[case["case_id"]]["question"],
                "candidate_answer": case["candidate_answer"],
            }
            if "top_k_pages" in case:
                view["top_k_pages"] = case["top_k_pages"]
            if "vista_package" in case:
                view["vista_package"] = case["vista_package"]
            views.append(view)
        return views
    # paired: rows already carry question + evidence + token.
    return [dict(row) for row in manifest["reviewer_view"][rkey]]


def queue_keys(day1_dir: Path, queue: str, manifest: dict) -> list[str]:
    return [cli._key_of_view(queue, v) for v in queue_views(day1_dir, queue, manifest)]


def signed_keys(day1_dir: Path, queue: str) -> list[str]:
    proto = protocol_for_manifest(_load_manifest(day1_dir))
    index, _ = cli.index_records(
        cli.load_records(record_file_path(day1_dir, proto, queue)),
        lambda r, q=queue: cli._key_of_record(q, r),
    )
    return sorted(index)


def _load_manifest(day1_dir: Path) -> dict:
    import json

    return json.loads((day1_dir / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))


def queue_record_types() -> dict[str, str]:
    return {
        "base": "BASE_22", "paired": "PAIRED_12",
        "interface": "INTERFACE_PILOT", "blind": "BLIND_REPEAT",
    }


def key_field(queue: str) -> str:
    return cli.QUEUE_KEY_FIELDS[queue]


def valid_evidence_ids_for(day1_dir: Path, queue: str, key: str, manifest: dict) -> frozenset[str]:
    """Evidence IDs permitted for one record's key (existence check, protocol-aware)."""
    if queue == "interface":
        return frozenset()
    cases = _cases_by_id(manifest)
    if queue == "base":
        case = cases.get(key)
        return frozenset(e["evidence_id"] for e in case.get("evidence_items", [])) if case else frozenset()
    if queue == "blind":
        proto = protocol_for_manifest(manifest)
        selection = {
            row["temp_id"]: row["case_id"]
            for row in manifest["sealed"][sealed_blind_key(proto)]
        }
        case = cases.get(selection.get(key, ""))
        return frozenset(e["evidence_id"] for e in case.get("evidence_items", [])) if case else frozenset()
    if queue == "paired":
        proto = protocol_for_manifest(manifest)
        for row in manifest["reviewer_view"][reviewer_key(proto, "paired")]:
            if row["review_token"] == key:
                return frozenset(e["evidence_id"] for e in row["evidence"])
        return frozenset()
    raise ValueError(f"unknown queue {queue!r}")


def manifest_protocol_id(manifest: dict) -> str:
    return protocol_for_manifest(manifest).protocol_id


def logical_queues() -> tuple[str, ...]:
    return LOGICAL_QUEUES
