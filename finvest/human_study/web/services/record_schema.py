"""Shared annotation record schema — single source of truth for web + CLI.

The authoritative schema lives in ``annotate_cli`` (BASE_FIELD_SPECS /
INTERFACE_FIELD_SPECS). This module derives the web form field contract from
that schema so the CLI validator and the web payload can never drift.

It also defines the queue-specific record field sets and the required
base fields (including ``minimal_evidence_set``, NOT ``minimal_evidence_ids``).
"""

from __future__ import annotations

from finvest.human_study import annotate_cli as cli

# The authoritative base field list (from the CLI validator).
BASE_FIELDS = [spec.name for spec in cli.BASE_FIELD_SPECS]
INTERFACE_FIELDS = [spec.name for spec in cli.INTERFACE_FIELD_SPECS]

# Queue-specific record types (must match CLI QUEUE_RECORD_TYPES).
RECORD_TYPES = {
    "base": "BASE_22",
    "paired": "PAIRED_12",
    "interface": "INTERFACE_PILOT",
    "blind": "BLIND_REPEAT",
}

# Queue-specific extra fields beyond the shared base fields.
QUEUE_EXTRA_FIELDS = {
    "base": (),
    "blind": ("temp_id", "pass"),
    "paired": ("review_token", "condition_identity", "pass"),
    "interface": (
        "display_condition", "final_judgement", "error_detected",
        "missing_evidence_detected", "wrong_period_detected",
        "review_time_seconds", "confidence", "interface_notes",
    ),
}

# The web form must emit these hidden fields (metadata that is prepopulated,
# not free-typed). minimal_evidence_set is the CLI-correct name.
HIDDEN_METADATA_FIELDS = (
    "case_id", "issuer", "source_cutoff", "target_period",
)

# Every base record requires these fields for CLI validation to pass.
REQUIRED_BASE_FIELDS = tuple(BASE_FIELDS)


def queue_record_fields(queue: str) -> tuple[str, ...]:
    """Full field list for a queue's record (base fields + queue extras)."""
    if queue == "interface":
        return tuple(INTERFACE_FIELDS)
    return tuple(BASE_FIELDS)


def contract_mapping() -> dict[str, dict[str, str]]:
    """Exact field-name mapping for the machine-readable contract test.

    Returns {queue: {html_field: record_field}}. The web form uses html_field
    names; the signing record uses record_field names.
    """
    mapping: dict[str, dict[str, str]] = {}
    for queue in ("base", "paired", "interface", "blind"):
        fields = queue_record_fields(queue)
        mapping[queue] = {field: field for field in fields}
    # Explicit: the web checkbox "minimal_evidence_ids" maps to the CLI
    # "minimal_evidence_set" field.
    mapping["base"]["minimal_evidence_ids"] = "minimal_evidence_set"
    mapping["blind"]["minimal_evidence_ids"] = "minimal_evidence_set"
    mapping["paired"]["minimal_evidence_ids"] = "minimal_evidence_set"
    return mapping


def validate_record_schema(queue: str, record: dict) -> list[str]:
    """Return missing-field problems for a record vs the queue's required fields."""
    required = queue_record_fields(queue)
    # For base-like queues (base/paired/blind), every base field is required.
    if queue in ("base", "paired", "blind"):
        missing = [f for f in BASE_FIELDS if f not in record]
    else:
        missing = [f for f in INTERFACE_FIELDS if f not in record]
    return missing
