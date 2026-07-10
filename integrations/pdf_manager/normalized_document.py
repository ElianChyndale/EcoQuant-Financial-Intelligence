import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date
from typing import Any

from ecoquant.document_intelligence.schema import EvidenceSpanV1


_LAYOUT_ROLES = {
    "title",
    "heading",
    "paragraph",
    "list_item",
    "caption",
    "header",
    "footer",
    "footnote",
    "page_number",
    "unknown",
}
_SEMANTIC_ROLES = {
    "body",
    "abstract",
    "reference",
    "metadata",
    "affiliation",
    "acknowledgement",
    "unknown",
}
_CONTINUATION_SOURCES = {"", "provider"}
_CONTINUATION_ROLES = {"", "single", "head", "middle", "tail"}
_CONTINUATION_SCOPES = {"", "intra_page", "cross_page"}


class NormalizedDocumentIngestionError(ValueError):
    """Raised when a normalized_document_v1 payload is structurally invalid."""


def load_normalized_document(
    payload: Mapping[str, Any],
    *,
    issuer_id: str,
    report_period: str,
    source_date: date,
) -> list[EvidenceSpanV1]:
    """Validate normalized_document_v1 and return stable evidence spans."""
    document = _mapping(payload, "payload")
    _require_equal(document, "schema", "normalized_document_v1")
    _require_equal(document, "schema_version", "1.1")
    document_id = _nonempty_string(document, "document_id", "payload")
    _mapping_value(document, "source", "payload")
    page_count = _nonnegative_int(document, "page_count", "payload")
    pages = _list_value(document, "pages", "payload")
    if len(pages) != page_count:
        raise NormalizedDocumentIngestionError("payload.page_count must match pages")
    derived = _mapping_value(document, "derived", "payload")
    confidence = _optional_confidence(derived, "confidence", "payload.derived")
    _mapping_value(document, "markers", "payload")

    ordered_blocks: list[tuple[int, int, int, Mapping[str, Any], Mapping[str, Any]]] = []
    page_indices: set[int] = set()
    for page_position, raw_page in enumerate(pages):
        page = _mapping(raw_page, f"payload.pages[{page_position}]")
        page_index = _nonnegative_int(page, "page_index", f"payload.pages[{page_position}]")
        if "page" in page:
            _minimum_int(page, "page", f"payload.pages[{page_position}]", minimum=1)
        if page_index in page_indices:
            raise NormalizedDocumentIngestionError("payload pages must have unique page_index values")
        page_indices.add(page_index)
        _nonnegative_number(page, "width", f"payload.pages[{page_position}]")
        _nonnegative_number(page, "height", f"payload.pages[{page_position}]")
        _require_equal(page, "unit", "pt")
        blocks = _list_value(page, "blocks", f"payload.pages[{page_position}]")
        for block_position, raw_block in enumerate(blocks):
            block = _validate_block(
                raw_block,
                page_index=page_index,
                location=f"payload.pages[{page_position}].blocks[{block_position}]",
            )
            reading_order = block.get("reading_order", block["order"])
            if not isinstance(reading_order, int) or isinstance(reading_order, bool) or reading_order < 0:
                raise NormalizedDocumentIngestionError("block.reading_order must be a non-negative integer")
            ordered_blocks.append((page_index, reading_order, block_position, page, block))

    spans: list[EvidenceSpanV1] = []
    for page_index, _, _, page, block in sorted(ordered_blocks, key=lambda item: item[:3]):
        content = _mapping_value(block, "content", "block")
        text = content.get("text")
        if not isinstance(text, str) or not text:
            continue
        bbox = _bbox(_mapping_value(block, "geometry", "block"), "bbox", "block.geometry")
        metadata = _mapping_value(block, "metadata", "block")
        section_value = metadata.get("section")
        if section_value is not None and not isinstance(section_value, str):
            raise NormalizedDocumentIngestionError("block.metadata.section must be a string or null")
        provider = _nonempty_string(
            _mapping_value(block, "provenance", "block"), "provider", "block.provenance"
        )
        page_id = str(page.get("page", page_index + 1))
        text_hash = _sha256(text)
        content_hash = _sha256_json(
            {
                "schema_version": "evidence-span.v1",
                "document_id": document_id,
                "issuer_id": issuer_id,
                "report_period": report_period,
                "source_date": source_date.isoformat(),
                "page_id": page_id,
                "block_id": block["block_id"],
                "bbox": bbox,
                "section": section_value,
                "text_hash": text_hash,
                "extraction_confidence": confidence,
                "provider": provider,
            }
        )
        spans.append(
            EvidenceSpanV1(
                schema_version="evidence-span.v1",
                document_id=document_id,
                issuer_id=issuer_id,
                report_period=report_period,
                source_date=source_date,
                page_id=page_id,
                block_id=block["block_id"],
                bbox=bbox,
                section=section_value,
                text=text,
                text_hash=text_hash,
                extraction_confidence=confidence,
                provider=provider,
                content_hash=content_hash,
            )
        )
    return spans


def _validate_block(raw_block: Any, *, page_index: int, location: str) -> Mapping[str, Any]:
    block = _mapping(raw_block, location)
    _nonempty_string(block, "block_id", location)
    if _nonnegative_int(block, "page_index", location) != page_index:
        raise NormalizedDocumentIngestionError(f"{location}.page_index must match its page")
    _nonnegative_int(block, "order", location)
    _bbox(_mapping_value(block, "geometry", location), "bbox", f"{location}.geometry")
    content = _mapping_value(block, "content", location)
    if content.get("kind") not in {"text", "image", "table", "formula", "code", "unknown"}:
        raise NormalizedDocumentIngestionError(f"{location}.content.kind is invalid")
    if "text" in content:
        _string(content, "text", f"{location}.content")
    _enum_string(block, "layout_role", location, _LAYOUT_ROLES)
    _enum_string(block, "semantic_role", location, _SEMANTIC_ROLES)
    _string(block, "structure_role", location)
    policy = _mapping_value(block, "policy", location)
    if not isinstance(policy.get("translate"), bool):
        raise NormalizedDocumentIngestionError(f"{location}.policy.translate must be a boolean")
    _string(policy, "translate_reason", f"{location}.policy")
    provenance = _mapping_value(block, "provenance", location)
    _nonempty_string(provenance, "provider", f"{location}.provenance")
    _string(provenance, "raw_label", f"{location}.provenance")
    _string(provenance, "raw_sub_type", f"{location}.provenance")
    _bbox(provenance, "raw_bbox", f"{location}.provenance")
    _string(provenance, "raw_path", f"{location}.provenance")
    _mapping_value(block, "metadata", location)
    source = _mapping_value(block, "source", location)
    _nonempty_string(source, "provider", f"{location}.source")
    continuation = _mapping_value(block, "continuation_hint", location)
    continuation_location = f"{location}.continuation_hint"
    _enum_string(continuation, "source", continuation_location, _CONTINUATION_SOURCES)
    _string(continuation, "group_id", continuation_location)
    _enum_string(continuation, "role", continuation_location, _CONTINUATION_ROLES)
    _enum_string(continuation, "scope", continuation_location, _CONTINUATION_SCOPES)
    _minimum_int(continuation, "reading_order", continuation_location, minimum=-1)
    _confidence(continuation, "confidence", continuation_location)
    return block


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256(encoded)


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizedDocumentIngestionError(f"{location} must be an object")
    return value


def _mapping_value(mapping: Mapping[str, Any], key: str, location: str) -> Mapping[str, Any]:
    if key not in mapping:
        raise NormalizedDocumentIngestionError(f"{location}.{key} is required")
    return _mapping(mapping[key], f"{location}.{key}")


def _list_value(mapping: Mapping[str, Any], key: str, location: str) -> list[Any]:
    if not isinstance(mapping.get(key), list):
        raise NormalizedDocumentIngestionError(f"{location}.{key} must be an array")
    return mapping[key]


def _string(mapping: Mapping[str, Any], key: str, location: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise NormalizedDocumentIngestionError(f"{location}.{key} must be a string")
    return value


def _nonempty_string(mapping: Mapping[str, Any], key: str, location: str) -> str:
    value = _string(mapping, key, location)
    if not value:
        raise NormalizedDocumentIngestionError(f"{location}.{key} must not be empty")
    return value


def _enum_string(
    mapping: Mapping[str, Any], key: str, location: str, allowed: set[str]
) -> str:
    value = _string(mapping, key, location)
    if value not in allowed:
        raise NormalizedDocumentIngestionError(f"{location}.{key} is invalid")
    return value


def _nonnegative_int(mapping: Mapping[str, Any], key: str, location: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise NormalizedDocumentIngestionError(f"{location}.{key} must be a non-negative integer")
    return value


def _nonnegative_number(mapping: Mapping[str, Any], key: str, location: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise NormalizedDocumentIngestionError(f"{location}.{key} must be a non-negative number")
    return float(value)


def _confidence(mapping: Mapping[str, Any], key: str, location: str) -> float:
    value = _nonnegative_number(mapping, key, location)
    if value > 1.0:
        raise NormalizedDocumentIngestionError(f"{location}.{key} must be within [0, 1]")
    return value


def _optional_confidence(mapping: Mapping[str, Any], key: str, location: str) -> float:
    if key not in mapping:
        return 0.0
    return _confidence(mapping, key, location)


def _bbox(mapping: Mapping[str, Any], key: str, location: str) -> tuple[float, float, float, float]:
    value = mapping.get(key)
    if not isinstance(value, list) or len(value) != 4:
        raise NormalizedDocumentIngestionError(f"{location}.{key} must contain four numbers")
    coordinates = []
    for coordinate in value:
        if not isinstance(coordinate, (int, float)) or isinstance(coordinate, bool) or not math.isfinite(coordinate):
            raise NormalizedDocumentIngestionError(f"{location}.{key} must contain four numbers")
        coordinates.append(float(coordinate))
    return tuple(coordinates)  # type: ignore[return-value]


def _minimum_int(
    mapping: Mapping[str, Any], key: str, location: str, *, minimum: int
) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise NormalizedDocumentIngestionError(f"{location}.{key} must be an integer no less than {minimum}")
    return value


def _require_equal(mapping: Mapping[str, Any], key: str, expected: str) -> None:
    if mapping.get(key) != expected:
        raise NormalizedDocumentIngestionError(f"payload.{key} must be {expected}")
