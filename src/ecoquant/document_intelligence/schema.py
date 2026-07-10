from dataclasses import dataclass
from datetime import date
import re


@dataclass(frozen=True)
class EvidenceSpanV1:
    schema_version: str
    document_id: str
    issuer_id: str
    report_period: str
    source_date: date
    page_id: str
    block_id: str
    bbox: tuple[float, float, float, float]
    section: str | None
    text: str
    text_hash: str
    extraction_confidence: float
    provider: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "evidence-span.v1":
            raise ValueError("schema_version must be evidence-span.v1")
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError("extraction_confidence must be within [0, 1]")
        if not _is_sha256(self.text_hash):
            raise ValueError("text_hash must be a lowercase SHA-256 hash")
        if not _is_sha256(self.content_hash):
            raise ValueError("content_hash must be a lowercase SHA-256 hash")


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
