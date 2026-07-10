import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from integrations.pdf_manager.normalized_document import (
    NormalizedDocumentIngestionError,
    load_normalized_document,
)


FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "normalized_document_v1.json"


def test_load_normalized_document_is_stable_and_preserves_reading_order() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    spans = load_normalized_document(
        payload,
        issuer_id="issuer-northstar",
        report_period="2024",
        source_date=date(2025, 3, 1),
    )
    repeated_spans = load_normalized_document(
        payload,
        issuer_id="issuer-northstar",
        report_period="2024",
        source_date=date(2025, 3, 1),
    )

    assert [span.block_id for span in spans] == ["block-2", "block-1"]
    assert [span.content_hash for span in spans] == [span.content_hash for span in repeated_spans]
    assert [span.text_hash for span in spans] == [span.text_hash for span in repeated_spans]

    relocated_payload = deepcopy(payload)
    relocated_payload["pages"][0]["blocks"][0]["provenance"]["raw_path"] = "alternate-source.pdf"
    relocated_spans = load_normalized_document(
        relocated_payload,
        issuer_id="issuer-northstar",
        report_period="2024",
        source_date=date(2025, 3, 1),
    )
    assert [span.content_hash for span in spans] == [span.content_hash for span in relocated_spans]


def test_load_normalized_document_rejects_structurally_malformed_extraction() -> None:
    payload = {
        "schema": "normalized_document_v1",
        "schema_version": "1.1",
        "document_id": "doc-malformed",
        "source": {},
        "page_count": 1,
        "pages": [
            {
                "page_index": 0,
                "width": 612,
                "height": 792,
                "unit": "pt",
                "blocks": [{"block_id": "incomplete-block"}],
            }
        ],
        "derived": {"role": "extraction", "by": "fixture", "confidence": 1.0},
        "markers": {},
    }

    with pytest.raises(NormalizedDocumentIngestionError, match="block"):
        load_normalized_document(
            payload,
            issuer_id="issuer-northstar",
            report_period="2024",
            source_date=date(2025, 3, 1),
        )


def test_load_normalized_document_accepts_contract_default_values() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["derived"] = {}
    payload["pages"][0]["blocks"][0]["structure_role"] = ""
    payload["pages"][0]["blocks"][0]["continuation_hint"]["reading_order"] = -1

    spans = load_normalized_document(
        payload,
        issuer_id="issuer-northstar",
        report_period="2024",
        source_date=date(2025, 3, 1),
    )

    assert [span.block_id for span in spans] == ["block-2", "block-1"]
    assert spans[0].extraction_confidence == 0.0


def test_load_normalized_document_emits_non_text_blocks_with_text_content() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pages"][0]["blocks"][0]["content"]["kind"] = "table"

    spans = load_normalized_document(
        payload,
        issuer_id="issuer-northstar",
        report_period="2024",
        source_date=date(2025, 3, 1),
    )

    assert [span.block_id for span in spans] == ["block-2", "block-1"]


def test_load_normalized_document_skips_blocks_without_text_content() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pages"][0]["blocks"][0]["content"].pop("text")

    spans = load_normalized_document(
        payload,
        issuer_id="issuer-northstar",
        report_period="2024",
        source_date=date(2025, 3, 1),
    )

    assert [span.block_id for span in spans] == ["block-2"]


def test_load_normalized_document_rejects_invalid_layout_role() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pages"][0]["blocks"][0]["layout_role"] = "invalid-layout-role"

    with pytest.raises(NormalizedDocumentIngestionError, match="layout_role"):
        load_normalized_document(
            payload,
            issuer_id="issuer-northstar",
            report_period="2024",
            source_date=date(2025, 3, 1),
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("source", "invalid-source"),
        ("role", "invalid-role"),
        ("scope", "invalid-scope"),
    ],
)
def test_load_normalized_document_rejects_invalid_continuation_enum(
    field: str, invalid_value: str
) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pages"][0]["blocks"][0]["continuation_hint"][field] = invalid_value

    with pytest.raises(NormalizedDocumentIngestionError, match=f"continuation_hint.{field}"):
        load_normalized_document(
            payload,
            issuer_id="issuer-northstar",
            report_period="2024",
            source_date=date(2025, 3, 1),
        )


def test_load_normalized_document_rejects_non_integer_page_value() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pages"][0]["page"] = "not-a-page-number"

    with pytest.raises(NormalizedDocumentIngestionError, match="page"):
        load_normalized_document(
            payload,
            issuer_id="issuer-northstar",
            report_period="2024",
            source_date=date(2025, 3, 1),
        )
