from datetime import date

import pytest

from ecoquant.document_intelligence.schema import EvidenceSpanV1


def test_evidence_span_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="extraction_confidence"):
        EvidenceSpanV1(
            schema_version="evidence-span.v1",
            document_id="doc-1",
            issuer_id="issuer-1",
            report_period="2024",
            source_date=date(2025, 3, 1),
            page_id="page-1",
            block_id="block-1",
            bbox=(0.0, 0.0, 10.0, 10.0),
            section="Allocation",
            text="Allocated proceeds were reported.",
            text_hash="0" * 64,
            extraction_confidence=1.1,
            provider="pdf-manager",
            content_hash="1" * 64,
        )


@pytest.mark.parametrize(
    ("hash_field", "invalid_hash"),
    [("text_hash", "A" * 64), ("content_hash", "not-a-sha256")],
)
def test_evidence_span_rejects_noncanonical_hashes(
    hash_field: str, invalid_hash: str
) -> None:
    values = {
        "schema_version": "evidence-span.v1",
        "document_id": "doc-1",
        "issuer_id": "issuer-1",
        "report_period": "2024",
        "source_date": date(2025, 3, 1),
        "page_id": "page-1",
        "block_id": "block-1",
        "bbox": (0.0, 0.0, 10.0, 10.0),
        "section": "Allocation",
        "text": "Allocated proceeds were reported.",
        "text_hash": "0" * 64,
        "extraction_confidence": 0.8,
        "provider": "pdf-manager",
        "content_hash": "1" * 64,
    }
    values[hash_field] = invalid_hash

    with pytest.raises(ValueError, match=hash_field):
        EvidenceSpanV1(**values)
