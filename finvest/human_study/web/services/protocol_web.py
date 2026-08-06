"""Web-layer protocol adaptation (Phase 12).

The annotation CLI is frozen on the v0.1 protocol (immutable, invalidated).
The workbench must be able to annotate the ACTIVE draft protocol (v0.2-draft)
whose queue names / record files differ (base_candidates vs base_22, etc.).

This module maps a frozen QUEUE_MANIFEST.json to its ProtocolConfig and
resolves the protocol-specific manifest keys and record filenames. It never
touches the CLI's v0.1 constants.
"""

from __future__ import annotations

from pathlib import Path

from finvest.human_study.protocol_config import V0_1, V0_2_DRAFT, ProtocolConfig

# Logical queue names used by the web layer (stable across protocols).
LOGICAL_QUEUES = ("base", "paired", "interface", "blind")


def protocol_for_manifest(manifest: dict) -> ProtocolConfig:
    """Resolve the ProtocolConfig for a frozen manifest.

    Matches by manifest_id first, then by the presence of protocol-specific
    sealed keys (defensive for hand-made manifests).
    """
    pid = manifest.get("manifest_id")
    if pid == V0_1.protocol_id:
        return V0_1
    if pid == V0_2_DRAFT.protocol_id:
        return V0_2_DRAFT
    sealed = manifest.get("sealed", {})
    if f"{V0_2_DRAFT.base_queue_name}_queue" in sealed:
        return V0_2_DRAFT
    return V0_1


def queue_name(proto: ProtocolConfig, queue: str) -> str:
    """Protocol queue name for a logical queue (base/paired/interface/blind)."""
    return {
        "base": proto.base_queue_name,
        "paired": proto.paired_queue_name,
        "interface": proto.interface_queue_name,
        "blind": proto.blind_queue_name,
    }[queue]


def record_file_name(proto: ProtocolConfig, queue: str) -> str:
    """Human-record filename for a logical queue under this protocol."""
    return {
        "base": proto.base_record_file,
        "paired": proto.paired_record_file,
        "interface": proto.interface_record_file,
        "blind": proto.blind_record_file,
    }[queue]


def record_file_path(day1_dir: Path, proto: ProtocolConfig, queue: str) -> Path:
    return day1_dir / record_file_name(proto, queue)


def sealed_key(proto: ProtocolConfig, queue: str) -> str:
    """Sealed manifest key for a logical queue (e.g. base_candidates_queue)."""
    return f"{queue_name(proto, queue)}_queue"


def reviewer_key(proto: ProtocolConfig, queue: str) -> str:
    """reviewer_view key for a logical queue (e.g. base_candidates)."""
    return queue_name(proto, queue)


def sealed_interface_key(proto: ProtocolConfig) -> str:
    return f"{proto.interface_queue_name}_cases"


def sealed_blind_key(proto: ProtocolConfig) -> str:
    return f"{proto.blind_queue_name}_selection"


def sealed_token_map_key(proto: ProtocolConfig) -> str:
    return f"{proto.paired_queue_name}_token_map"


def base_queue(manifest: dict) -> list[dict]:
    """Sealed base cases for the manifest's protocol."""
    proto = protocol_for_manifest(manifest)
    return list(manifest.get("sealed", {}).get(sealed_key(proto, "base"), []))
