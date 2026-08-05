"""FinVEST document intelligence: SEC EDGAR HTML 10-K -> evidence units.

Parses a full 10-K HTML document into section/paragraph evidence units with
stable IDs, keeping table structure (not flattening it). Each unit carries the
document/version metadata needed by the benchmark (valid/source time, section).

Evidence-unit granularity:
- Section (top-level heading) → paragraph evidence units.
- Table → table evidence units (rows preserved).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser

from finvest.benchmark.schemas import EvidenceItem

_HEADING_RE = re.compile(r"^(item\s*\d+|part\s*[ivx]+)", re.IGNORECASE)
_SECTION_START = re.compile(r"^(item\s*\d+[ab]?\.?)", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDocument:
    document_id: str
    document_version: str
    filing_date: date
    sections: tuple[str, ...]
    evidence_units: tuple[EvidenceItem, ...]


class _HtmlTextExtractor(HTMLParser):
    """Extract text with block boundaries; keep table cells as rows."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._current: list[str] = []
        self._in_table = False
        self._in_row = False
        self._row_cells: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "tr", "table"):
            self._flush()
        if tag == "table":
            self._in_table = True
        elif tag == "tr":
            self._in_row = True
            self._row_cells = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("p", "div", "h1", "h2", "h3", "h4"):
            self._flush()
        elif tag in ("td", "th"):
            cell = " ".join("".join(self._current).split())
            if cell:
                self._row_cells.append(cell)
            self._current = []
            self._in_cell = False
        elif tag == "tr":
            if self._row_cells:
                self.blocks.append(" | ".join(self._row_cells))
            self._row_cells = []
            self._in_row = False
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data: str) -> None:
        self._current.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._current).split())
        if text:
            self.blocks.append(text)
        self._current = []


def parse_10k_html(
    html_path: object,
    *,
    document_id: str,
    document_version: str,
    filing_date: date,
) -> ParsedDocument:
    """Parse a SEC EDGAR 10-K HTML file into evidence units."""
    import pathlib

    path = pathlib.Path(html_path)
    extractor = _HtmlTextExtractor()
    extractor.feed(path.read_text(encoding="utf-8", errors="ignore"))
    blocks = extractor.blocks

    units: list[EvidenceItem] = []
    current_section = "front"
    for index, block in enumerate(blocks):
        lowered = block.lower()
        if _SECTION_START.match(lowered):
            current_section = lowered[:40]
        units.append(EvidenceItem(
            evidence_id=f"{document_id}:{index:05d}",
            document_id=document_id,
            document_version=document_version,
            filing_date=filing_date,
            valid_from=filing_date,
            section=current_section,
            text_span=block[:500],
            content_hash=f"{document_id}:{index:05d}",
        ))
    return ParsedDocument(
        document_id=document_id,
        document_version=document_version,
        filing_date=filing_date,
        sections=tuple(sorted({u.section or "front" for u in units})),
        evidence_units=tuple(units),
    )
