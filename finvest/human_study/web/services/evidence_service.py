"""Evidence resolution service — resolves ORIGINAL local source material.

The sealed manifest stores evidence descriptors with ``text_span``/``table_id``
often null. This service resolves the original text/table/XBRL from the local
SEC cache (gitignored raw files). It NEVER fabricates replacement evidence.

If original evidence cannot be resolved, it returns an explicit
``EVIDENCE_RESOLUTION_FAILED`` state with the exact missing asset — never a
generated substitute.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

RESOLUTION_FAILED = "EVIDENCE_RESOLUTION_FAILED"


@dataclass(frozen=True)
class EvidenceView:
    evidence_id: str
    concept: str
    document_id: str
    document_version: str
    filing_date: str
    valid_from: str | None
    unit: str | None
    scale: str | None
    scope: str | None
    resolution_status: str  # "resolved" | RESOLUTION_FAILED
    missing_asset: str | None = None
    text_excerpt: str | None = None
    table_rows: list[list[str]] = field(default_factory=list)
    table_headers: list[str] = field(default_factory=list)
    xbrl: dict | None = None


def _safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _resolve_from_html_10k(evidence: dict, cache: Path) -> EvidenceView | None:
    """Try to find the concept/number in the company's full 10-K HTML."""
    issuer = evidence.get("document_id", "").split("-")[0].lower()
    full_10k = cache / "sec" / "full_10k"
    candidates = [
        p for p in full_10k.glob("*.htm")
        if p.stem.lower().startswith(issuer)
    ]
    if not candidates:
        return None
    concept = evidence.get("concept", "")
    for path in candidates:
        text = _safe_read(path)
        # Locate a paragraph/section containing the concept label.
        idx = text.find(concept)
        if idx < 0:
            # Try a humanized variant (CamelCase -> words).
            humanized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", concept)
            idx = text.find(humanized)
        if idx >= 0:
            excerpt = _excerpt(text, idx)
            return EvidenceView(
                evidence_id=evidence["evidence_id"],
                concept=concept,
                document_id=evidence.get("document_id") or "",
                document_version=evidence.get("document_version") or "",
                filing_date=evidence.get("filing_date") or "",
                valid_from=evidence.get("valid_from"),
                unit=evidence.get("unit"),
                scale=evidence.get("scale"),
                scope=evidence.get("scope"),
                resolution_status="resolved",
                text_excerpt=excerpt,
                xbrl=evidence,
            )
    return None


def _excerpt(text: str, idx: int, width: int = 600) -> str:
    start = max(0, idx - width // 3)
    end = min(len(text), idx + width)
    return text[start:end].replace("\n", " ").strip()


def resolve_evidence(evidence: dict, cache: Path) -> EvidenceView:
    """Resolve one evidence item's original source, or report the failure."""
    # XBRL fact from companyfacts JSON is the most authoritative.
    xbrl = _resolve_from_companyfacts(evidence, cache)
    if xbrl is not None:
        return xbrl
    html = _resolve_from_html_10k(evidence, cache)
    if html is not None:
        return html
    # No original source found — explicit failure, no fabricated fallback.
    return EvidenceView(
        evidence_id=evidence["evidence_id"],
        concept=evidence.get("concept") or "",
        document_id=evidence.get("document_id") or "",
        document_version=evidence.get("document_version") or "",
        filing_date=evidence.get("filing_date") or "",
        valid_from=evidence.get("valid_from"),
        unit=evidence.get("unit"),
        scale=evidence.get("scale"),
        scope=evidence.get("scope"),
        resolution_status=RESOLUTION_FAILED,
        missing_asset=f"full_10k/{evidence.get('document_id','?')}.htm or companyfacts concept "
                      f"{evidence.get('concept')}",
    )


def _resolve_from_companyfacts(evidence: dict, cache: Path) -> EvidenceView | None:
    """Resolve an XBRL fact from the companyfacts JSON."""
    issuer = evidence.get("document_id", "").split("-")[0].lower()
    concept = evidence.get("concept", "")
    path = cache / "sec" / f"{issuer}_companyfacts.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for taxonomy, concepts in payload.get("facts", {}).items():
        if concept not in concepts:
            continue
        for unit, facts in concepts[concept].get("units", {}).items():
            for fact in facts:
                if str(fact.get("end")) == evidence.get("valid_from") or (
                    evidence.get("xbrl_fact_id") and fact.get("val") is not None
                ):
                    return EvidenceView(
                        evidence_id=evidence["evidence_id"],
                        concept=concept,
                        document_id=evidence.get("document_id") or "",
                        document_version=fact.get("form") or evidence.get("document_version", ""),
                        filing_date=fact.get("filed") or evidence.get("filing_date", ""),
                        valid_from=fact.get("end") or evidence.get("valid_from"),
                        unit=unit,
                        scale=evidence.get("scale"),
                        scope=evidence.get("scope"),
                        resolution_status="resolved",
                        xbrl={
                            "concept": concept,
                            "label": concepts[concept].get("label"),
                            "value": fact.get("val"),
                            "unit": unit,
                            "start": fact.get("start"),
                            "end": fact.get("end"),
                            "form": fact.get("form"),
                            "filed": fact.get("filed"),
                            "frame": fact.get("frame"),
                            "source_fact_id": evidence.get("xbrl_fact_id"),
                        },
                    )
    return None


def resolve_evidence_set(evidence_items: list[dict], cache: Path) -> list[EvidenceView]:
    return [resolve_evidence(item, cache) for item in evidence_items]
