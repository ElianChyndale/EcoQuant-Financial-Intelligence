"""Adapter: FinVEST data <-> financial-ai-contracts (Phase 5.1).

Maps FinVEST case payloads, resolved evidence rows, and experiment output into
the versioned financial-ai-contracts records (BenchmarkCase / EvidenceUnit /
ExperimentRecord), validated against their canonical JSON + SHA-256.

FAC identifiers are lowercase-only (regex ^[a-z0-9][a-z0-9._:-]{2,127}$);
FinVEST ids contain uppercase (finvest-AAPL-..., AAPL:us-gaap:...). We
normalize via a stable slug mapping. This is a data-shape adapter: the first
phase does NOT change the FAC schema; once the mapping stabilizes, schema 1.1
can be published.

All tool imports are lazy so CI without financial-ai-contracts still passes.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from typing import Any


def _identifier(text: str) -> str:
    """Lowercase slug for a FinVEST identifier (reversible via side mapping)."""
    slug = re.sub(r"[^a-z0-9._:-]", "-", text.lower())
    slug = re.sub(r"^-+|-+$", "", slug)
    if not slug or len(slug) < 3:
        slug = "finvest-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return slug


def _document_hash(document_id: str) -> str:
    """Bytes32 from a document_id (0x + sha256 hex)."""
    return "0x" + hashlib.sha256(document_id.encode("utf-8")).hexdigest()


def _aware_utc(d: date | datetime | str | None) -> datetime:
    """UTC-aware datetime from a date/datetime/iso string."""
    if d is None:
        d = date(1970, 1, 1)
    if isinstance(d, datetime):
        return d.astimezone(UTC) if d.tzinfo else d.replace(tzinfo=UTC)
    if isinstance(d, date):
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    text = str(d)[:10]
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _question_type(answer_type: str | None) -> str:
    mapping = {
        "derived": "numerical",
        "extractive": "factual",
        "comparative": "comparison",
        "unanswerable": "unanswerable",
        "temporal": "temporal",
        "conflict": "conflict",
    }
    return mapping.get(answer_type or "", "factual")


def finvest_case_to_benchmark_case(case: dict[str, Any]) -> Any:
    """Map a FinVEST sealed case payload -> contracts.BenchmarkCase."""
    from financial_ai_contracts.models import BenchmarkCase, GoldAnswer

    gold = case.get("gold_answer") or {}
    gold_value = gold.get("value")
    gold_unit = gold.get("unit")
    answerable = gold_value is not None or bool(gold)

    gold_answer = None
    if answerable:
        unit = "currency" if gold_unit == "USD" else None
        gold_answer = GoldAnswer(
            text=str(gold_value or ""),
            numeric_value=_decimal_str(gold_value) if gold_value is not None else None,
            unit=unit,
            currency="USD" if gold_unit == "USD" else None,
        )

    document_ids = sorted({it.get("document_id") for it in (case.get("evidence_items") or []) if it.get("document_id")})
    evidence_ids = [it.get("evidence_id") for it in (case.get("evidence_items") or []) if it.get("evidence_id")]

    return BenchmarkCase(
        case_id=_identifier(case["case_id"]),
        question=case["question"],
        question_type=_question_type(case.get("answer_type")),
        answerable=answerable,
        gold_answer=gold_answer,
        document_ids=[_identifier(d) for d in document_ids] or [_identifier(case["case_id"])],
        gold_evidence_ids=[_identifier(e) for e in evidence_ids],
        abstention_expected=not answerable,
        unanswerable_reasons=[] if answerable else ["no sufficient public evidence"],
        split="test",
        synthetic=True,
    )


def _decimal_str(value: Any) -> str:
    """Canonical decimal string from a float/int."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return f"{value:.0f}" if float(value).is_integer() else str(float(value))


def evidence_item_to_evidence_unit(item: dict[str, Any]) -> Any:
    """Map a resolved evidence row (raw_rows-style) -> contracts.EvidenceUnit."""
    from financial_ai_contracts.models import EvidenceUnit, TimeInterval

    text = item.get("text_span") or " ".join(
        str(item.get(k, "")) for k in ("concept", "val", "unit")
        if item.get(k) is not None
    )
    source_time = _aware_utc(item.get("filed"))
    valid_start = _aware_utc(item.get("start")) if item.get("start") else source_time
    valid_end = _aware_utc(item.get("end")) if item.get("end") else None

    return EvidenceUnit(
        evidence_id=_identifier(item.get("evidence_id") or item.get("concept") or "evidence"),
        document_id=_identifier(item.get("document_id") or item.get("source_file") or "doc"),
        document_hash=_document_hash(item.get("document_id") or item.get("source_file") or "doc"),
        page=1,
        section=None,
        text=text[:19999] or ".",
        bounding_box=None,
        source_time=source_time,
        valid_time=TimeInterval(start=valid_start, end=valid_end),
        issuer_id=_identifier(item.get("issuer") or "") if item.get("issuer") else None,
        bond_id=None,
    )


def experiment_output_to_experiment_record(
    output: dict[str, Any],
    *,
    experiment_id: str,
    seed: int,
    commit: str,
    model_version: str = "finvest-a11-v1",
    prompt_version: str = "a11-two-stage.v1",
) -> Any:
    """Map the A11 experiment output -> contracts.ExperimentRecord.

    Extracts the aggregate decision counts as metrics. ``commit`` must be a
    40/64-hex git sha.
    """
    from financial_ai_contracts.models import EnvironmentInfo, ExperimentRecord, MetricValue

    decisions = output.get("decisions", {})
    metrics = [
        MetricValue(name="n_cases", value=_decimal_str(output.get("n_cases", 0)), unit="count"),
        MetricValue(name="answer", value=_decimal_str(decisions.get("ANSWER", 0)), unit="count"),
        MetricValue(name="review", value=_decimal_str(decisions.get("REVIEW", 0)), unit="count"),
        MetricValue(name="abstain", value=_decimal_str(decisions.get("ABSTAIN", 0)), unit="count"),
    ]
    agg = output.get("answer_agreement", {})
    metrics.append(MetricValue(name="answer_agreement_rate", value=_decimal_str(agg.get("rate", 0.0)), unit="ratio"))

    limitations = list(output.get("markers", [])) or ["SOLO_PROVISIONAL"]
    if not limitations:
        limitations = ["not paper headline"]

    dep_lock = hashlib.sha256(
        json_dumps_canonical(output).encode("utf-8")
    ).hexdigest()

    return ExperimentRecord(
        experiment_id=_identifier(experiment_id),
        dataset_version=str(output.get("corpus", {}).get("corpus_id", "unknown"))[:128],
        model_version=model_version,
        prompt_version=prompt_version,
        retriever="R1_bm25/R2_dense/R3_rrf/R4_concept",
        seed=seed,
        metrics=metrics,
        commit=commit,
        environment=EnvironmentInfo(
            runtime="python3.13",
            platform="win32",
            dependency_lock_hash="0x" + dep_lock,
        ),
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 2, tzinfo=UTC),
        limitations=limitations[:10],
    )


def json_dumps_canonical(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def record_hash(record: Any) -> str:
    """Canonical SHA-256 of a contracts record (reuses FAC canonicalization)."""
    from financial_ai_contracts.canonical import record_hash as fac_hash

    return fac_hash(record.model_dump(mode="json", by_alias=True))


def validate_record(record: Any, contract_type: str) -> None:
    """Validate a contracts record against its JSON schema + semantic rules."""
    from financial_ai_contracts.validation import validate_record as fac_validate

    fac_validate(record.model_dump(mode="json", by_alias=True), contract_type=contract_type)
