"""Tooling-issue workflow (Phase 7).

A reported tooling issue is stored SEPARATELY from human labels. It never
creates a label and never modifies the frozen queue. The researcher moves to
the next READY case after reporting.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ISSUE_CATEGORIES = (
    "MISSING_VALUE",
    "MISSING_UNIT",
    "METADATA_INCONSISTENCY",
    "EVIDENCE_RESOLUTION_FAILED",
    "VERSION_TIMELINE_MISSING",
    "WRONG_CONCEPT_DISPLAYED",
    "UI_ACTION_FAILED",
    "INVALID_BENCHMARK_CASE",
    "OTHER_TOOLING_ISSUE",
)


def report_tooling_issue(
    *,
    issue_path: Path,
    case_id: str,
    queue: str,
    evidence_id: str | None,
    category: str,
    note: str,
    reviewer_id: str,
    commit: str,
    request_id: str,
) -> Path:
    """Store one tooling-issue report (not a label). Returns the report path."""
    if category not in ISSUE_CATEGORIES:
        raise ValueError(f"unknown issue category: {category}")
    entry = {
        "case_id": case_id,
        "queue": queue,
        "evidence_id": evidence_id,
        "issue_category": category,
        "researcher_note": note,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "application_commit": commit,
        "request_id": request_id,
        "reviewer_id": reviewer_id,
        "is_human_label": False,
    }
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    with issue_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return issue_path
