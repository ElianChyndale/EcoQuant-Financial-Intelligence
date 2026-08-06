"""Strictly neutral, human-controlled annotation CLI (day-1 pilot).

This module is the ONLY sanctioned way to enter human labels for the day-1
pilot. It enforces the scientific boundary:

NEVER:
- infer, recommend, or display candidate labels, model predictions, scores,
  or prior annotations in annotation flows (base / paired / blind);
- auto-sign a record;
- change frozen queues, QUEUE_MANIFEST.json, or frozen hashes;
- write reviewer notes (the researcher's notes pass through untouched);
- silently fill a missing field.

ONLY:
- display frozen questions and permitted evidence descriptors;
- explain field definitions (from SCHEMA.md) in prompts;
- collect literal human input;
- validate field types, allowed enum values, and evidence-ID existence;
- save unsigned drafts (Ctrl+C-safe);
- show the completed draft back to the researcher;
- request explicit typed signing (``SIGN <key>``);
- append a valid signed record to the correct JSONL;
- resume from the first unfinished case.

Interface-pilot exception: the ``interface`` queue displays the frozen
interface content (candidate answer, top-k pages, VISTA package) because the
researcher reviews the INTERFACE output itself — that artifact is under test
(SINGLE_REVIEWER_USABILITY_PILOT, NO_HUMAN_EFFECTIVENESS_CLAIM). Annotation
flows never do this.

Honesty markers: EXPLORATORY_PILOT · SMALL_SAMPLE · NOT_PAPER_HEADLINE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from finvest.human_study.day1_pilot import (
    DAY1_DIR,
    PILOT_MARKERS,
    canonical_json,
    sha256_hex,
    verify_frozen,
)

# Frozen protocol: blind repeat only >= 4 hours after ALL 22 base labels are
# signed (ANNOTATION_GUIDELINE.md §4.5).
BLIND_MIN_WAIT_HOURS = 4

QUEUES = ("base", "paired", "interface", "blind")
QUEUE_RECORD_TYPES = {
    "base": "BASE_22",
    "paired": "PAIRED_12",
    "interface": "INTERFACE_PILOT",
    "blind": "BLIND_REPEAT",
}
QUEUE_KEY_FIELDS = {
    "base": "case_id",
    "paired": "review_token",
    "interface": "case_id",
    "blind": "temp_id",
}
QUEUE_TITLES = {
    "base": "Base case",
    "paired": "Paired case",
    "interface": "Interface case",
    "blind": "Blind repeat (pass 2)",
}
RECORD_FILES = {
    "base": "BASE_22_HUMAN_SIGNED.jsonl",
    "paired": "PAIRED_12_HUMAN_SIGNED.jsonl",
    "interface": "INTERFACE_PILOT_9.jsonl",
    "blind": "BLIND_REPEAT_5.jsonl",
}

# Keys that must never appear in annotation display output (projection).
FORBIDDEN_DISPLAY_KEYS = (
    "gold_answer", "decision_label", "sufficiency_label",
    "acceptable_evidence_sets", "minimal_evidence_sets",
    "calculation_program", "known_conflicts", "answer_type",
    "version_relations", "prohibited_claims", "assumptions",
)


class CliError(Exception):
    """A user-facing error; printed as ``error: ...`` and exit code 1."""


class IOProtocol(Protocol):
    def input(self, prompt: str = "") -> str: ...  # pragma: no cover

    def print(self, text: str = "") -> None: ...  # pragma: no cover


class RealIO:
    """Real stdin/stdout adapter."""

    def input(self, prompt: str = "") -> str:
        return input(prompt)

    def print(self, text: str = "") -> None:
        print(text)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# Field schema (copied from SCHEMA.md; validation only — never fills values)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # enum | text | list | id_list | bool | number | confidence | answer | notes
    enum: tuple[str, ...] = ()
    allow_unresolved: bool = False


BASE_FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec("question_valid", "enum", ("VALID", "AMBIGUOUS", "INVALID"), True),
    FieldSpec("answerability", "enum", ("ANSWERABLE", "UNANSWERABLE"), True),
    FieldSpec("sufficiency", "enum",
              ("SUPPORTED", "PARTIAL", "INSUFFICIENT", "CONFLICTING", "REFUTED"), True),
    FieldSpec("entity", "text"),
    FieldSpec("metric", "text"),
    FieldSpec("target_period", "text"),
    FieldSpec("unit_and_scale", "text"),
    FieldSpec("reporting_scope", "text"),
    FieldSpec("mandatory_requirements", "list"),
    FieldSpec("supporting_evidence_ids", "id_list"),
    FieldSpec("minimal_evidence_set", "id_list"),
    FieldSpec("source_time_valid", "bool"),
    FieldSpec("version_valid", "bool"),
    FieldSpec("calculation_reproducible", "bool"),
    FieldSpec("final_answer_or_null", "answer"),
    FieldSpec("reviewer_confidence", "confidence"),
    FieldSpec("reviewer_notes", "notes"),
    FieldSpec("elapsed_seconds", "number"),
)

INTERFACE_FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec("final_judgement", "enum",
              ("ACCEPT", "ACCEPT_WITH_RESERVATIONS", "REJECT"), True),
    FieldSpec("error_detected", "bool"),
    FieldSpec("missing_evidence_detected", "bool"),
    FieldSpec("wrong_period_detected", "bool"),
    FieldSpec("review_time_seconds", "number"),
    FieldSpec("confidence", "confidence"),
    FieldSpec("interface_notes", "notes"),
    FieldSpec("elapsed_seconds", "number"),
)


def _hint(spec: FieldSpec) -> str:
    if spec.kind == "enum":
        hint = "/".join(spec.enum)
        if spec.allow_unresolved:
            hint += "/REVIEW_UNRESOLVED"
        return hint + "/blank"
    if spec.kind == "text":
        return "text or blank"
    if spec.kind == "list":
        return "comma/space-separated"
    if spec.kind == "id_list":
        return "evidence IDs (comma/space-separated)"
    if spec.kind == "bool":
        return "true/false/blank"
    if spec.kind == "number":
        return "number"
    if spec.kind == "confidence":
        return "1-5 or blank"
    if spec.kind == "answer":
        return "number, text, or blank"
    if spec.kind == "notes":
        return "free text or blank"
    return spec.kind


def _split_items(raw: str) -> list[str]:
    return [item for item in raw.replace(",", " ").split()]


def _parse(spec: FieldSpec, raw: str, valid_ids: frozenset[str]) -> Any:
    """Parse one literal input; raise ValueError with a human message."""
    if spec.kind == "enum":
        value = raw.strip().upper()
        if not value:
            return None
        if spec.allow_unresolved and value == "REVIEW_UNRESOLVED":
            return value
        if value in spec.enum:
            return value
        allowed = "/".join(spec.enum)
        if spec.allow_unresolved:
            allowed += "/REVIEW_UNRESOLVED"
        raise ValueError(f"must be one of: {allowed} (or blank)")
    if spec.kind == "text":
        value = raw.strip()
        return value or None
    if spec.kind == "list":
        return _split_items(raw)
    if spec.kind == "id_list":
        items = _split_items(raw)
        unknown = [item for item in items if item not in valid_ids]
        if unknown:
            raise ValueError(
                f"unknown evidence IDs: {', '.join(unknown)} "
                "(enter IDs from the evidence list above)"
            )
        return items
    if spec.kind == "bool":
        value = raw.strip().lower()
        if not value:
            return None
        if value in ("true", "t", "yes", "y"):
            return True
        if value in ("false", "f", "no", "n"):
            return False
        raise ValueError("must be true, false, or blank")
    if spec.kind == "number":
        value = raw.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            raise ValueError("must be a number") from None
    if spec.kind == "confidence":
        value = raw.strip()
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError("must be an integer 1-5 or blank") from None
        if not 1 <= parsed <= 5:
            raise ValueError("must be an integer 1-5 or blank")
        return parsed
    if spec.kind == "answer":
        value = raw.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return value
    if spec.kind == "notes":
        value = raw.strip()
        return value or None
    raise ValueError(f"unknown field kind: {spec.kind}")


def _check_value(spec: FieldSpec, value: Any, valid_ids: frozenset[str]) -> str | None:
    """Validate a stored value; return an error message or None."""
    if value is None:
        return None
    if spec.kind == "enum":
        if spec.allow_unresolved and value == "REVIEW_UNRESOLVED":
            return None
        if value in spec.enum:
            return None
        return f"invalid value {value!r} (allowed: {', '.join(spec.enum)})"
    if spec.kind == "text":
        return None if isinstance(value, str) else "must be text or null"
    if spec.kind == "list":
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return None
        return "must be a list of strings"
    if spec.kind == "id_list":
        if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            return "must be a list of strings"
        unknown = [v for v in value if v not in valid_ids]
        if unknown:
            return f"unknown evidence IDs: {', '.join(unknown)}"
        return None
    if spec.kind == "bool":
        return None if isinstance(value, bool) else "must be true/false/null"
    if spec.kind == "number":
        if isinstance(value, bool):
            return "must be a number"
        return None if isinstance(value, (int, float)) else "must be a number"
    if spec.kind == "confidence":
        return None if isinstance(value, int) and 1 <= value <= 5 else "must be an integer 1-5"
    if spec.kind == "answer":
        if isinstance(value, bool):
            return "must be number/text/null"
        return None if isinstance(value, (str, int, float)) else "must be number/text/null"
    if spec.kind == "notes":
        return None if isinstance(value, str) else "must be text or null"
    return f"unknown field kind: {spec.kind}"


def _fmt_current(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def collect_fields(
    specs: tuple[FieldSpec, ...],
    io: IOProtocol,
    *,
    valid_ids: frozenset[str] = frozenset(),
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect literal human input with type/enum/evidence-ID validation.

    ``defaults`` supplies displayed current values (used by ``correct`` for
    editing and by measured elapsed seconds); a blank input keeps a default.
    Nothing is ever silently invented.
    """
    defaults = defaults or {}
    values: dict[str, Any] = {}
    for spec in specs:
        while True:
            current = defaults.get(spec.name)
            prompt = f"{spec.name} [{_hint(spec)}]"
            if current is not None:
                prompt += f" (current: {_fmt_current(current)})"
            raw = io.input(prompt + ": ")
            if raw.strip() == "" and current is not None:
                values[spec.name] = current
                break
            try:
                values[spec.name] = _parse(spec, raw, valid_ids)
                break
            except ValueError as exc:
                io.print(f"  invalid: {exc}")
    return values


# ---------------------------------------------------------------------------
# Views (display projections — candidate content never leaves the sealed side)
# ---------------------------------------------------------------------------

def _descriptor(item: dict[str, Any]) -> dict[str, Any]:
    keys = ("evidence_id", "document_id", "document_version", "filing_date",
            "valid_from", "concept", "unit", "scale", "scope")
    return {k: item.get(k) for k in keys}


def project_case(case: dict[str, Any]) -> dict[str, Any]:
    """Permitted display projection of a sealed case dict.

    Only question, issuer, cutoff, target period, evidence descriptors, and
    source file paths. Never gold/decision/sufficiency/program content.
    """
    evidence = [_descriptor(item) for item in case.get("evidence_items", [])]
    target = case.get("target_fiscal_year") or case.get("target_period_end")
    return {
        "case_id": case["case_id"],
        "question": case["question"],
        "issuer": case["issuer_id"],
        "source_cutoff": case.get("source_cutoff"),
        "target_period": target,
        "evidence": evidence,
        "source_files": [
            f"research/cache/sec/{case['issuer_id'].lower()}_companyfacts.json",
            "research/cache/sec/full_10k/",
        ],
    }


def _print_evidence(io: IOProtocol, items: list[dict[str, Any]]) -> None:
    io.print("Evidence:")
    if not items:
        io.print("  (no evidence descriptor in the manifest — verify directly "
                 "against the SEC source files above)")
        return
    keys = ("evidence_id", "document_id", "document_version", "filing_date",
            "valid_from", "concept", "unit", "scale", "scope")
    for item in items:
        parts = [str(item[k]) for k in keys if item.get(k) is not None]
        io.print("  - " + " | ".join(parts))


def display_view(io: IOProtocol, queue: str, view: dict[str, Any]) -> None:
    """Display the frozen review materials only (no candidate content)."""
    if queue in ("base", "blind"):
        io.print(f"Question: {view['question']}")
        io.print(f"Issuer: {view['issuer']}")
        io.print(f"Source cutoff: {view['source_cutoff']}")
        io.print(f"Target period: {view['target_period']}")
        io.print("Permitted sources: " + " · ".join(view["source_files"]))
        _print_evidence(io, view["evidence"])
    elif queue == "paired":
        io.print(f"Question: {view['question']}")
        io.print("Condition identity: hidden during review")
        _print_evidence(io, view["evidence"])
    elif queue == "interface":
        # Interface pilot: the interface output IS the artifact under review.
        io.print(f"Display condition: {view['display_condition']}")
        io.print(f"Question: {view['question']}")
        io.print("Candidate answer: " + json.dumps(view["candidate_answer"], default=str))
        if "top_k_pages" in view:
            io.print("Top-k pages: " + json.dumps(view["top_k_pages"], default=str))
        if "vista_package" in view:
            io.print("VISTA package: " + json.dumps(view["vista_package"], default=str))
    else:
        raise CliError(f"unknown queue {queue!r}")


def _views(manifest: dict[str, Any], queue: str) -> list[dict[str, Any]]:
    """Frozen-order views for one queue (reviewer-sheet order)."""
    cases = {c["case_id"]: c for c in manifest["sealed"]["base_22_queue"]}
    if queue == "base":
        return [
            project_case(cases[row["case_id"]])
            for row in manifest["reviewer_view"]["base_22"]
        ]
    if queue == "paired":
        return manifest["reviewer_view"]["paired_12"]
    if queue == "interface":
        views = []
        for case in manifest["sealed"]["interface_9_cases"]:
            view: dict[str, Any] = {
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
    if queue == "blind":
        selection = {
            row["temp_id"]: row["case_id"]
            for row in manifest["sealed"]["blind_repeat_5_selection"]
        }
        return [
            {"temp_id": row["temp_id"], **project_case(cases[selection[row["temp_id"]]])}
            for row in manifest["reviewer_view"]["blind_repeat_5"]
        ]
    raise CliError(f"unknown queue {queue!r}")


def _key_of_view(queue: str, view: dict[str, Any]) -> str:
    return view[QUEUE_KEY_FIELDS[queue]]


def _key_of_record(queue: str, record: dict[str, Any]) -> str | None:
    return record.get(QUEUE_KEY_FIELDS[queue])


def _valid_evidence_ids_for_record(
    queue: str, key: str, manifest: dict[str, Any]
) -> frozenset[str]:
    """Evidence IDs permitted for one record's key (existence check)."""
    if queue == "interface":
        return frozenset()
    cases = {c["case_id"]: c for c in manifest["sealed"]["base_22_queue"]}
    if queue == "base":
        case = cases.get(key)
        if case is None:
            return frozenset()
        return frozenset(e["evidence_id"] for e in case.get("evidence_items", []))
    if queue == "blind":
        selection = {
            row["temp_id"]: row["case_id"]
            for row in manifest["sealed"]["blind_repeat_5_selection"]
        }
        case = cases.get(selection.get(key, ""))
        if case is None:
            return frozenset()
        return frozenset(e["evidence_id"] for e in case.get("evidence_items", []))
    if queue == "paired":
        for row in manifest["reviewer_view"]["paired_12"]:
            if row["review_token"] == key:
                return frozenset(e["evidence_id"] for e in row["evidence"])
        return frozenset()
    raise CliError(f"unknown queue {queue!r}")


# ---------------------------------------------------------------------------
# Draft storage (Ctrl+C-safe: drafts hit disk immediately after collection)
# ---------------------------------------------------------------------------

def drafts_dir(day1_dir: Path) -> Path:
    return day1_dir / "drafts"


def draft_path(day1_dir: Path, key: str) -> Path:
    return drafts_dir(day1_dir) / f"draft-{key}.json"


def save_draft(day1_dir: Path, key: str, payload: dict[str, Any]) -> Path:
    path = draft_path(day1_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def load_draft(day1_dir: Path, key: str) -> dict[str, Any] | None:
    path = draft_path(day1_dir, key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def remove_draft(day1_dir: Path, key: str) -> None:
    path = draft_path(day1_dir, key)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Signed-record storage (append-only; never overwritten)
# ---------------------------------------------------------------------------

def record_file(day1_dir: Path, queue: str) -> Path:
    return day1_dir / RECORD_FILES[queue]


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"__malformed__": line})
    return records


def index_records(
    records: list[dict[str, Any]], key_of: Any
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Last-record-wins index plus duplicate keys (duplicates = corrections)."""
    index: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for record in records:
        if "__malformed__" in record:
            continue
        key = key_of(record)
        if key is None:
            continue
        if key in index:
            duplicates.append(key)
        index[key] = record
    return index, duplicates


def signed_index(path: Path, queue: str) -> dict[str, dict[str, Any]]:
    index, _ = index_records(
        load_records(path), lambda r: _key_of_record(queue, r)
    )
    return index


def _append_record(day1_dir: Path, queue: str, record: dict[str, Any]) -> None:
    path = record_file(day1_dir, queue)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def _compose_draft(
    queue: str, key: str, view: dict[str, Any], fields: dict[str, Any]
) -> dict[str, Any]:
    draft: dict[str, Any] = {
        "queue": queue,
        "record_type": QUEUE_RECORD_TYPES[queue],
    }
    if queue in ("base", "interface"):
        draft["case_id"] = key
    elif queue == "paired":
        draft["review_token"] = key
        draft["condition_identity"] = "HIDDEN_DURING_REVIEW"
        draft["pass"] = 1
    elif queue == "blind":
        draft["temp_id"] = key
        draft["pass"] = 2
    if queue == "interface":
        draft["display_condition"] = view["display_condition"]
    draft.update(fields)
    return draft


# ---------------------------------------------------------------------------
# Record validation (schema + evidence-ID existence; AI never fills values)
# ---------------------------------------------------------------------------

def record_problems(
    queue: str, key: str, record: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    """Schema/existence problems for one signed record (empty = valid)."""
    problems: list[str] = []
    if record.get("record_type") != QUEUE_RECORD_TYPES[queue]:
        problems.append(f"record_type must be {QUEUE_RECORD_TYPES[queue]}")
    if record.get(QUEUE_KEY_FIELDS[queue]) != key:
        problems.append(f"{QUEUE_KEY_FIELDS[queue]} must be {key!r}")
    if queue == "paired":
        if record.get("condition_identity") != "HIDDEN_DURING_REVIEW":
            problems.append("condition_identity must be HIDDEN_DURING_REVIEW")
        if record.get("pass") != 1:
            problems.append("pass must be 1")
    if queue == "blind":
        if record.get("pass") != 2:
            problems.append("pass must be 2")
    if queue == "interface":
        allowed = ("answer_only", "answer_topk_pages", "answer_vista_package")
        if record.get("display_condition") not in allowed:
            problems.append("display_condition not in " + "/".join(allowed))
    specs = BASE_FIELD_SPECS if queue != "interface" else INTERFACE_FIELD_SPECS
    valid_ids = _valid_evidence_ids_for_record(queue, key, manifest)
    for spec in specs:
        if spec.name not in record:
            problems.append(f"missing field: {spec.name}")
            continue
        error = _check_value(spec, record[spec.name], valid_ids)
        if error:
            problems.append(f"{spec.name}: {error}")
    if not record.get("signed_by") or not isinstance(record["signed_by"], str):
        problems.append("missing signed_by (human signature required)")
    if not record.get("timestamp"):
        problems.append("missing timestamp (human signature required)")
    else:
        try:
            _parse_ts(record["timestamp"])
        except ValueError:
            problems.append("timestamp is not ISO-8601")
    if record.get("signed") is not True:
        problems.append("signed must be true")
    return problems


# ---------------------------------------------------------------------------
# Signing (explicit typed confirmation; timestamp is mechanical, not a label)
# ---------------------------------------------------------------------------

def _confirm_and_append(
    manifest: dict[str, Any],
    queue: str,
    key: str,
    draft: dict[str, Any],
    reviewer_id: str,
    io: IOProtocol,
    day1_dir: Path,
    expected_word: str,
    now: datetime | None,
) -> dict[str, Any] | None:
    """Show the completed draft, require typed confirmation, append signed."""
    io.print("--- Completed draft (exact) ---")
    io.print(json.dumps(draft, indent=2, sort_keys=True, default=str))
    while True:
        answer = io.input(
            f"Type {expected_word} {key} to proceed, or SKIP to keep the draft: "
        ).strip()
        if answer == f"{expected_word} {key}":
            record = dict(draft)
            record["signed"] = True
            record["signed_by"] = reviewer_id
            record["timestamp"] = (now or _utcnow()).isoformat(timespec="seconds")
            problems = record_problems(queue, key, record, manifest)
            if problems:
                raise CliError("record invalid, nothing appended: " + "; ".join(problems))
            _append_record(day1_dir, queue, record)
            remove_draft(day1_dir, key)
            io.print(
                f"signed by {reviewer_id}; appended to {RECORD_FILES[queue]}"
            )
            return record
        if answer == "SKIP":
            io.print("draft kept; nothing appended")
            return None
        io.print(f"  invalid: type {expected_word} <key> or SKIP")


# ---------------------------------------------------------------------------
# Blind-repeat gate (frozen protocol: all 22 base signed, then >= 4h wait)
# ---------------------------------------------------------------------------

def blind_earliest(
    manifest: dict[str, Any], day1_dir: Path, now: datetime | None = None
) -> tuple[bool, str]:
    """(ready, human-readable reason) for the blind repeat (pass 2)."""
    now = now or _utcnow()
    base_index = signed_index(record_file(day1_dir, "base"), "base")
    if len(base_index) < 22:
        return False, (
            f"pending: {len(base_index)}/22 base labels signed (all 22 "
            f"required, then +{BLIND_MIN_WAIT_HOURS}h)"
        )
    timestamps = [_parse_ts(record["timestamp"]) for record in base_index.values()]
    latest = max(timestamps)
    earliest = latest + timedelta(hours=BLIND_MIN_WAIT_HOURS)
    if now >= earliest:
        return True, f"eligible (earliest was {earliest.isoformat()})"
    remaining = earliest - now
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes = remainder // 60
    return False, (
        f"not before {earliest.isoformat()} (wait remaining: "
        f"{hours}h {minutes}m; protocol requires +{BLIND_MIN_WAIT_HOURS}h "
        f"after all 22 base labels are signed)"
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@dataclass
class AnnotateOptions:
    reviewer_id: str
    resume: bool = False
    limit: int | None = None
    case_id: str | None = None
    start_at: str | None = None


def run_annotate(
    manifest: dict[str, Any],
    queue: str,
    opts: AnnotateOptions,
    io: IOProtocol,
    day1_dir: Path = DAY1_DIR,
    now: datetime | None = None,
) -> int:
    """Interactive annotation session; returns count signed this run."""
    if queue not in QUEUES:
        raise CliError(f"unknown queue {queue!r}")
    if not opts.reviewer_id.strip():
        raise CliError("--reviewer-id is required (the signing identifier)")
    if queue == "blind":
        ready, reason = blind_earliest(manifest, day1_dir, now)
        if not ready:
            raise CliError(f"blind repeat unavailable: {reason}")
    views = _views(manifest, queue)
    keys = [_key_of_view(queue, view) for view in views]
    if opts.start_at is not None:
        if opts.start_at not in keys:
            raise CliError(f"--start-at {opts.start_at!r} is not in the {queue} queue")
        views = views[keys.index(opts.start_at):]
    if opts.case_id is not None:
        if opts.case_id not in keys:
            raise CliError(f"--case-id {opts.case_id!r} is not in the {queue} queue")
        views = [views[keys.index(opts.case_id)]]
    signed = signed_index(record_file(day1_dir, queue), queue)
    if not opts.resume:
        # When a specific case is targeted, only that key blocks a fresh run;
        # otherwise any signed key in the queue blocks (forces explicit --resume).
        guard_keys = [opts.case_id] if opts.case_id is not None else keys
        in_scope = [key for key in guard_keys if key in signed]
        if in_scope:
            raise CliError(
                f"already signed and --resume not given: {in_scope}; "
                "use --resume, or `correct` for amendments"
            )
    io.print(f"queue: {queue}  ·  markers: {' · '.join(PILOT_MARKERS)}")
    signed_count = 0
    processed = 0
    for view in views:
        key = _key_of_view(queue, view)
        if opts.resume and key in signed:
            io.print(f"skip {key} (already signed)")
            continue
        if opts.limit is not None and processed >= opts.limit:
            break
        if _run_case(manifest, queue, view, key, opts, io, day1_dir, now):
            signed_count += 1
        processed += 1
    io.print(f"{processed} case(s) processed; {signed_count} signed this run")
    return signed_count


def _run_case(
    manifest: dict[str, Any],
    queue: str,
    view: dict[str, Any],
    key: str,
    opts: AnnotateOptions,
    io: IOProtocol,
    day1_dir: Path,
    now: datetime | None,
) -> bool:
    """Display -> collect -> validate -> save draft -> show -> request signing."""
    io.print("")
    io.print(f"=== {QUEUE_TITLES[queue]}: {key} ===")
    display_view(io, queue, view)
    started = now or _utcnow()
    elapsed_default = round((now or _utcnow() - started).total_seconds(), 1)
    specs = INTERFACE_FIELD_SPECS if queue == "interface" else BASE_FIELD_SPECS
    defaults: dict[str, Any] = {
        "elapsed_seconds": elapsed_default,
    }
    if queue == "interface":
        defaults["review_time_seconds"] = defaults["elapsed_seconds"]
    valid_ids = _valid_evidence_ids_for_record(queue, key, manifest)
    fields = collect_fields(specs, io, valid_ids=valid_ids, defaults=defaults)
    draft = _compose_draft(queue, key, view, fields)
    save_draft(day1_dir, key, draft)
    io.print(f"draft saved: {draft_path(day1_dir, key)}")
    return (
        _confirm_and_append(manifest, queue, key, draft, opts.reviewer_id,
                            io, day1_dir, "SIGN", now)
        is not None
    )


def run_review_draft(day1_dir: Path, key: str, io: IOProtocol) -> None:
    """Display one unsigned draft exactly as stored, without suggestions."""
    path = draft_path(day1_dir, key)
    if not path.exists():
        raise CliError(f"no unsigned draft for {key!r}")
    io.print(path.read_text(encoding="utf-8").rstrip("\n"))


def run_sign(
    manifest: dict[str, Any],
    day1_dir: Path,
    key: str,
    reviewer_id: str,
    io: IOProtocol,
    now: datetime | None = None,
) -> int:
    """Sign a saved unsigned draft (typed SIGN <key> + reviewer ID + UTC)."""
    if not reviewer_id.strip():
        raise CliError("--reviewer-id is required")
    # Refuse a signed key BEFORE requiring a draft: a signed record has no
    # draft, and records must never be overwritten (test #7).
    for candidate_queue in QUEUES:
        index = signed_index(record_file(day1_dir, candidate_queue), candidate_queue)
        if key in index:
            raise CliError(f"{key} is already signed; use `correct` for amendments")
    path = draft_path(day1_dir, key)
    if not path.exists():
        raise CliError(f"no unsigned draft for {key!r} (run annotate first)")
    draft = json.loads(path.read_text(encoding="utf-8"))
    queue = draft.get("queue")
    if queue not in QUEUES:
        raise CliError(f"draft has no valid queue: {queue!r}")
    if draft.get(QUEUE_KEY_FIELDS[queue]) != key:
        raise CliError(
            f"draft key mismatch: {QUEUE_KEY_FIELDS[queue]} "
            f"{draft.get(QUEUE_KEY_FIELDS[queue])!r} != {key!r}"
        )
    io.print("--- Unsigned draft (exact) ---")
    io.print(path.read_text(encoding="utf-8").rstrip("\n"))
    draft = dict(draft)
    if draft.get("elapsed_seconds") is None:
        while True:
            raw = io.input("elapsed_seconds [number]: ")
            try:
                parsed = float(raw.strip())
                if raw.strip():
                    draft["elapsed_seconds"] = parsed
                break
            except ValueError:
                io.print("  invalid: must be a number")
    return 1 if (
        _confirm_and_append(manifest, queue, key, draft, reviewer_id,
                            io, day1_dir, "SIGN", now)
        is not None
    ) else 0


def run_correct(
    manifest: dict[str, Any],
    day1_dir: Path,
    queue: str,
    key: str,
    reviewer_id: str,
    reason: str,
    io: IOProtocol,
    now: datetime | None = None,
) -> int:
    """Amend a signed record: append new record + audit entry (never overwrite)."""
    if queue not in QUEUES:
        raise CliError(f"unknown queue {queue!r}")
    if not reviewer_id.strip():
        raise CliError("--reviewer-id is required")
    if not reason.strip():
        raise CliError("--reason is required for corrections")
    path = record_file(day1_dir, queue)
    index = signed_index(path, queue)
    old = index.get(key)
    if old is None:
        raise CliError(f"no signed record for {key!r} in queue {queue!r}")
    io.print("--- Current signed record ---")
    io.print(json.dumps(old, indent=2, sort_keys=True, default=str))
    view = next(
        (v for v in _views(manifest, queue) if _key_of_view(queue, v) == key),
        {},
    )
    specs = INTERFACE_FIELD_SPECS if queue == "interface" else BASE_FIELD_SPECS
    defaults = {spec.name: old.get(spec.name) for spec in specs if spec.name in old}
    valid_ids = _valid_evidence_ids_for_record(queue, key, manifest)
    io.print("Enter corrected values; blank keeps the current value:")
    fields = collect_fields(specs, io, valid_ids=valid_ids, defaults=defaults)
    draft = _compose_draft(queue, key, view, fields)
    save_draft(day1_dir, key, draft)
    new = _confirm_and_append(manifest, queue, key, draft, reviewer_id,
                              io, day1_dir, "CORRECT", now)
    if new is None:
        return 0
    _append_audit(day1_dir, key, queue, old, new, reason, reviewer_id, now)
    io.print("audit entry appended to CORRECTIONS_AUDIT.jsonl")
    return 1


def _append_audit(
    day1_dir: Path,
    key: str,
    queue: str,
    old: dict[str, Any],
    new: dict[str, Any],
    reason: str,
    reviewer_id: str,
    now: datetime | None,
) -> None:
    entry = {
        "key": key,
        "queue": queue,
        "old_record_hash": sha256_hex(canonical_json(old)),
        "new_record_hash": sha256_hex(canonical_json(new)),
        "reason": reason,
        "correction_timestamp": (now or _utcnow()).isoformat(timespec="seconds"),
        "signed_by": reviewer_id,
    }
    path = day1_dir / "CORRECTIONS_AUDIT.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _audit_keys(day1_dir: Path) -> set[tuple[str, str]]:
    path = day1_dir / "CORRECTIONS_AUDIT.jsonl"
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        keys.add((entry.get("queue"), entry.get("key")))
    return keys


def load_manifest(day1_dir: Path = DAY1_DIR) -> dict[str, Any]:
    path = day1_dir / "QUEUE_MANIFEST.json"
    if not path.exists():
        raise CliError(f"no frozen manifest at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_status(
    manifest: dict[str, Any],
    io: IOProtocol,
    day1_dir: Path = DAY1_DIR,
    now: datetime | None = None,
) -> int:
    """Annotation status: counts, drafts, blind gate, violations."""
    counts: dict[str, int] = {}
    problems: list[str] = []
    corrections = _audit_keys(day1_dir)
    all_signed: dict[str, dict[str, Any]] = {}
    for queue in QUEUES:
        index = signed_index(record_file(day1_dir, queue), queue)
        counts[queue] = len(index)
        all_signed.update(index)
        _, duplicates = index_records(
            load_records(record_file(day1_dir, queue)),
            lambda r, q=queue: _key_of_record(q, r),
        )
        for key in duplicates:
            if (queue, key) not in corrections:
                problems.append(f"{queue}/{key}: corrected record without audit entry")
        for key, record in index.items():
            for problem in record_problems(queue, key, record, manifest):
                problems.append(f"{queue}/{key}: {problem}")
    drafts = sorted(path.name for path in drafts_dir(day1_dir).glob("draft-*.json"))
    for name in drafts:
        key = name[len("draft-"):-len(".json")]
        if key in all_signed:
            problems.append(f"draft exists for signed key {key!r}")
    ready, blind_reason = blind_earliest(manifest, day1_dir, now)
    frozen = verify_frozen(day1_dir)
    problems.extend(frozen["violations"])
    io.print("Day-1 pilot status "
             f"(markers: {' · '.join(PILOT_MARKERS)})")
    io.print(f"  base signed:            {counts['base']} / 22")
    io.print(f"  paired signed:          {counts['paired']} / 12")
    io.print(f"  interface signed:       {counts['interface']} / 9")
    io.print(f"  blind (pass 2) signed:  {counts['blind']} / 5")
    io.print(f"  unsigned drafts:        {len(drafts)}")
    io.print(f"  earliest blind repeat:  {blind_reason}")
    if problems:
        io.print(f"  violations:             {len(problems)}")
        for problem in problems:
            io.print(f"    - {problem}")
    else:
        io.print("  violations:             0")
    return 0
