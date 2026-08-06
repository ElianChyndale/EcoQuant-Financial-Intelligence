"""Protocol configuration — single source of truth for versioned pilot protocols.

Drives manifest IDs, versions, case counts, queue names, and record filenames
so no code hardcodes ``0.1.0`` / ``22`` / ``base_22_queue``. v0.1 is an
immutable, invalidated artifact; v0.2 is a draft until scientifically frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Root of the human-review tree.
HUMAN_REVIEW_ROOT = Path(__file__).resolve().parents[3] / "human_review"


@dataclass(frozen=True)
class ProtocolConfig:
    protocol_id: str          # e.g. "v0.1", "v0.2-draft", "v0.2"
    manifest_version: str     # e.g. "0.1.0", "0.2.0-draft"
    base_queue_name: str      # queue name in manifest (not "base_22")
    base_record_file: str     # human-record filename
    paired_queue_name: str
    paired_record_file: str
    blind_queue_name: str
    blind_record_file: str
    interface_queue_name: str
    interface_record_file: str
    min_base_cases: int       # minimum valid base cases (derived, not a frozen 22)
    expected_base_cases: int | None = None  # exact when frozen

    @property
    def dir(self) -> Path:
        """The protocol's own directory under human_review/day1/."""
        return HUMAN_REVIEW_ROOT / "day1" / self.protocol_id


# v0.1 — immutable, INVALIDATED_BENCHMARK_CONSTRUCTION. Read-only.
V0_1 = ProtocolConfig(
    protocol_id="v0.1",
    manifest_version="0.1.0",
    base_queue_name="base_22",
    base_record_file="BASE_22_HUMAN_SIGNED.jsonl",
    paired_queue_name="paired_12",
    paired_record_file="PAIRED_12_HUMAN_SIGNED.jsonl",
    blind_queue_name="blind_repeat_5",
    blind_record_file="BLIND_REPEAT_5.jsonl",
    interface_queue_name="interface_9",
    interface_record_file="INTERFACE_PILOT_9.jsonl",
    min_base_cases=22,
    expected_base_cases=22,
)

# v0.2 — DRAFT until scientific freeze. Never hardcoded 22.
V0_2_DRAFT = ProtocolConfig(
    protocol_id="v0.2-draft",
    manifest_version="0.2.0-draft",
    base_queue_name="base_candidates",
    base_record_file="BASE_HUMAN_SIGNED.jsonl",
    paired_queue_name="paired_candidates",
    paired_record_file="PAIRED_HUMAN_SIGNED.jsonl",
    blind_queue_name="blind_repeat",
    blind_record_file="BLIND_REPEAT.jsonl",
    interface_queue_name="interface_candidates",
    interface_record_file="INTERFACE_PILOT.jsonl",
    min_base_cases=1,          # derived from valid data, not a fixed 22
    expected_base_cases=None,  # frozen later
)


def active_draft_config() -> ProtocolConfig:
    """Return the active draft protocol (v0.2-draft until scientifically frozen)."""
    return V0_2_DRAFT
