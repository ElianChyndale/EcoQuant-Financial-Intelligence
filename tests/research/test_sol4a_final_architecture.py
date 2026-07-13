from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from ecoquant.document_intelligence.schema import EvidenceSpanV1
from ecoquant.retrieval import base as retrieval_base
from ecoquant.retrieval.base import CorpusRecord, corpus_fingerprint
from ecoquant.retrieval.corpus_adapter import AuthoritativeCorpus, adapt_evidence_spans
from ecoquant.evidence_graph.builder import build_graph
from ecoquant.retrieval.base import RetrieverQuery
from ecoquant.retrieval.kg import StaticKGRetriever


def _span(
    *,
    document_id: str = "document-1",
    page_id: str = "7",
    block_id: str = "block-9",
    text: str = "Exact Café assets 100.00",
    content_hash: str = "c" * 64,
    source_date: date = date(2024, 3, 1),
    report_period: str = "2023",
) -> EvidenceSpanV1:
    return EvidenceSpanV1(
        schema_version="evidence-span.v1",
        document_id=document_id,
        issuer_id="AIB",
        report_period=report_period,
        source_date=source_date,
        page_id=page_id,
        block_id=block_id,
        bbox=(1.0, 2.0, 3.0, 4.0),
        section="Assets",
        text=text,
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        extraction_confidence=0.95,
        provider="pdf-manager",
        content_hash=content_hash,
    )


class TestAuthoritativeCorpusAdapter:
    def test_document_id_changes_canonical_bytes_and_hash(self) -> None:
        left = adapt_evidence_spans((_span(document_id="document-a"),))
        right = adapt_evidence_spans((_span(document_id="document-b"),))

        assert retrieval_base.canonical_corpus_bytes(left.records) != retrieval_base.canonical_corpus_bytes(
            right.records
        )
        assert corpus_fingerprint(left.records) != corpus_fingerprint(right.records)

    def test_adapter_preserves_identity_location_text_and_times(self) -> None:
        span = _span()
        corpus = adapt_evidence_spans(
            (span,),
            source_ids={span.content_hash: "source-system-42"},
            asset_ids={span.content_hash: "asset-aib"},
            valid_to={span.content_hash: date(2024, 12, 31)},
            structured_values={
                span.content_hash: {"reported_assets": Decimal("100.00")},
            },
        )

        assert type(corpus) is AuthoritativeCorpus
        record = corpus.records[0]
        assert record.schema_version == "retrieval-corpus-record.v3"
        assert record.source_schema_version == "evidence-span.v1"
        assert record.evidence_id == span.content_hash
        assert record.document_id == span.document_id
        assert record.source_id == "source-system-42"
        assert record.issuer == span.issuer_id
        assert record.asset_id == "asset-aib"
        assert record.text == span.text
        assert record.valid_from == date(2023, 12, 31)
        assert record.valid_to == date(2024, 12, 31)
        assert record.source_time == span.source_date
        assert record.page_id == span.page_id
        assert record.block_id == span.block_id
        assert record.structured_values == (("reported_assets", Decimal("100.00")),)

    def test_repeated_conversion_is_deterministic(self) -> None:
        spans = (_span(content_hash="a" * 64), _span(block_id="block-10", content_hash="b" * 64))

        first = adapt_evidence_spans(spans)
        second = adapt_evidence_spans(reversed(spans))

        assert first.records == second.records
        assert retrieval_base.canonical_corpus_bytes(first.records) == retrieval_base.canonical_corpus_bytes(
            second.records
        )

    def test_missing_document_id_fails_production_adaptation(self) -> None:
        with pytest.raises(ValueError, match="document_id"):
            adapt_evidence_spans((_span(document_id=""),))

    def test_authoritative_corpus_cannot_be_constructed_by_caller(self) -> None:
        with pytest.raises(TypeError, match="adapt_evidence_spans"):
            AuthoritativeCorpus((CorpusRecord("e", "AIB", date(2023, 12, 31), "text"),))

    def test_schema_v3_bytes_include_every_adapter_semantic_field(self) -> None:
        span = _span()
        corpus = adapt_evidence_spans((span,))

        payload = retrieval_base.json.loads(retrieval_base.canonical_corpus_bytes(corpus.records))[0]

        assert payload["schema_version"] == "retrieval-corpus-record.v3"
        assert payload["source_schema_version"] == span.schema_version
        assert payload["document_id"] == span.document_id
        assert payload["page_id"] == span.page_id
        assert payload["block_id"] == span.block_id
        assert payload["text"] == span.text
        assert payload["valid_from"] == "2023-12-31"
        assert payload["source_time"] == span.source_date.isoformat()
        assert payload["bbox"] == ["0x1.0000000000000p+0", "0x1.0000000000000p+1", "0x1.8000000000000p+1", "0x1.0000000000000p+2"]

    def test_graph_document_candidate_resolves_to_adapted_span_record(self) -> None:
        span = _span(text="AIB assets")
        corpus = adapt_evidence_spans((span,))
        graph = build_graph((span,))
        method = StaticKGRetriever(corpus.records, cutoff=date(2024, 12, 31), graph=graph)
        query = RetrieverQuery("q1", "AIB", "assets", date(2024, 12, 31))

        results = method.retrieve(query)

        assert [result.evidence_id for result in results] == [span.content_hash]


@pytest.mark.parametrize(
    "value",
    (
        np.float16("0.1"),
        np.float32("0.1"),
        np.float64("0.1"),
        np.int32(1),
        np.int64(1),
    ),
    ids=("float16", "float32", "float64", "int32", "int64"),
)
def test_authoritative_numeric_identity_rejects_numpy_scalars(value: object) -> None:
    record = CorpusRecord("e", "AIB", date(2023, 12, 31), "text", value)

    with pytest.raises(ValueError, match="built-in Python|NumPy"):
        retrieval_base.canonical_corpus_bytes((record,))


class _UnsupportedScalar:
    pass


def test_authoritative_numeric_identity_rejects_unsupported_scalar() -> None:
    record = CorpusRecord("e", "AIB", date(2023, 12, 31), "text", _UnsupportedScalar())

    with pytest.raises(ValueError, match="built-in Python|unsupported"):
        retrieval_base.canonical_corpus_bytes((record,))


@pytest.mark.parametrize(
    "value",
    (
        np.float16("nan"),
        np.float32("inf"),
        np.float64("-inf"),
    ),
)
def test_nonfinite_numpy_values_are_rejected_as_unsupported_scalars(value: object) -> None:
    record = CorpusRecord("e", "AIB", date(2023, 12, 31), "text", value)

    with pytest.raises(ValueError, match="NumPy"):
        retrieval_base.canonical_corpus_bytes((record,))


class _EqualToEverything:
    def __eq__(self, other: object) -> bool:
        return True

    def __bool__(self) -> bool:
        return True


class _StringSubclass(str):
    pass


@pytest.mark.parametrize(
    "value",
    (
        _EqualToEverything(),
        _StringSubclass("a" * 64),
        "A" * 64,
        "0x" + "a" * 64,
        "a" * 63,
        "a" * 65,
        " " + "a" * 64,
        "g" * 64,
    ),
    ids=(
        "custom-equality-object",
        "string-subclass",
        "uppercase",
        "hex-prefix",
        "short",
        "long",
        "whitespace",
        "non-hex",
    ),
)
def test_strict_fingerprint_value_rejects_malformed_values(value: object) -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        retrieval_base.validate_fingerprint_value(value)


def test_strict_fingerprint_value_accepts_exact_builtin_lowercase_sha256() -> None:
    value = "0123456789abcdef" * 4

    assert retrieval_base.validate_fingerprint_value(value) == value
