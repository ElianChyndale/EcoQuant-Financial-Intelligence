"""Authoritative EvidenceSpanV1 to retrieval-corpus construction boundary."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date
from typing import overload
from uuid import uuid4

from ecoquant.document_intelligence.schema import EvidenceSpanV1

from .base import CORPUS_RECORD_SCHEMA_VERSION, CorpusNumericValue, CorpusRecord, canonical_corpus_bytes


_ADAPTER_SEAL = object()


class AuthoritativeCorpus(Sequence[CorpusRecord]):
    """Sealed immutable corpus produced only by :func:`adapt_evidence_spans`."""

    __slots__ = ("_records", "_adapter_receipt_id", "_seal")

    def __init__(
        self,
        records: tuple[CorpusRecord, ...],
        *,
        _seal: object | None = None,
        _adapter_receipt_id: str | None = None,
    ) -> None:
        if _seal is not _ADAPTER_SEAL or _adapter_receipt_id is None:
            raise TypeError("AuthoritativeCorpus must be created by adapt_evidence_spans")
        self._records = records
        self._adapter_receipt_id = _adapter_receipt_id
        self._seal = _seal

    @property
    def records(self) -> tuple[CorpusRecord, ...]:
        return self._records

    @overload
    def __getitem__(self, index: int) -> CorpusRecord: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[CorpusRecord, ...]: ...

    def __getitem__(self, index: int | slice) -> CorpusRecord | tuple[CorpusRecord, ...]:
        return self._records[index]

    def __iter__(self) -> Iterator[CorpusRecord]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)


def adapt_evidence_spans(
    spans: Iterable[EvidenceSpanV1],
    *,
    source_ids: Mapping[str, str] | None = None,
    asset_ids: Mapping[str, str] | None = None,
    valid_to: Mapping[str, date | None] | None = None,
    structured_values: Mapping[str, Mapping[str, CorpusNumericValue]] | None = None,
) -> AuthoritativeCorpus:
    """Map validated evidence spans to one sealed deterministic production corpus."""

    evidence = tuple(spans)
    if not evidence:
        raise ValueError("authoritative evidence corpus must not be empty")
    if not all(type(span) is EvidenceSpanV1 for span in evidence):
        raise TypeError("authoritative corpus adaptation requires EvidenceSpanV1 values")

    identifiers = [span.content_hash for span in evidence]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("EvidenceSpanV1 content_hash values must be unique evidence IDs")
    known = frozenset(identifiers)
    supplied_mappings: tuple[Mapping[str, object], ...] = tuple(
        mapping
        for mapping in (source_ids, asset_ids, valid_to, structured_values)
        if mapping is not None
    )
    for mapping in supplied_mappings:
        unknown = set(mapping) - known
        if unknown:
            raise ValueError(f"adapter metadata references unknown evidence IDs: {sorted(unknown)}")

    records: list[CorpusRecord] = []
    for span in sorted(evidence, key=lambda item: item.content_hash):
        _require_nonempty(span.document_id, "document_id")
        _require_nonempty(span.content_hash, "content_hash")
        _require_nonempty(span.issuer_id, "issuer_id")
        _require_nonempty(span.page_id, "page_id")
        _require_nonempty(span.block_id, "block_id")
        _require_nonempty(span.text, "text")
        valid_from = _report_period_end(span.report_period)
        end = valid_to.get(span.content_hash) if valid_to is not None else None
        if end is not None and end < valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        values = structured_values.get(span.content_hash, {}) if structured_values else {}
        if any(type(name) is not str or not name for name in values):
            raise ValueError("structured numerical value names must be non-empty built-in strings")

        records.append(CorpusRecord(
            evidence_id=span.content_hash,
            issuer=span.issuer_id,
            valid_time=valid_from,
            text=span.text,
            numeric_value=None,
            source_time=span.source_date,
            schema_version=CORPUS_RECORD_SCHEMA_VERSION,
            source_schema_version=span.schema_version,
            document_id=span.document_id,
            source_id=source_ids.get(span.content_hash) if source_ids else None,
            asset_id=asset_ids.get(span.content_hash, span.issuer_id) if asset_ids else span.issuer_id,
            valid_to=end,
            page_id=span.page_id,
            block_id=span.block_id,
            report_period=span.report_period,
            bbox=span.bbox,
            section=span.section,
            text_hash=span.text_hash,
            content_hash=span.content_hash,
            extraction_confidence=span.extraction_confidence,
            provider=span.provider,
            structured_values=tuple(sorted(values.items())),
        ))

    frozen_records = tuple(records)
    canonical_corpus_bytes(frozen_records)
    return AuthoritativeCorpus(
        frozen_records,
        _seal=_ADAPTER_SEAL,
        _adapter_receipt_id=uuid4().hex,
    )


def _authoritative_corpus_receipt(corpus: object) -> tuple[str, tuple[CorpusRecord, ...]]:
    """Return internal adapter evidence for the production factory."""

    if type(corpus) is not AuthoritativeCorpus or corpus._seal is not _ADAPTER_SEAL:
        raise ValueError("production retrieval requires an adapter-produced AuthoritativeCorpus")
    return corpus._adapter_receipt_id, corpus.records


def _require_nonempty(value: object, field_name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"EvidenceSpanV1 {field_name} must be a non-empty built-in string")


def _report_period_end(report_period: str) -> date:
    try:
        return date.fromisoformat(report_period)
    except ValueError:
        pass
    if len(report_period) == 4 and report_period.isdigit():
        return date(int(report_period), 12, 31)
    raise ValueError("report_period must be an ISO date or four-digit year")
