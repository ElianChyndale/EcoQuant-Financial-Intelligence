"""Committed synthetic full 10-K HTML fixture (Phase 8).

Unit/workflow tests that need a *document-level* corpus must depend ONLY on
this committed fixture — never the gitignored SEC cache. It is a small but
faithful 10-K-shaped HTML document whose text mentions the exact fact values
from ``sec_companyfacts_fixture.json`` (Assets 400, Revenues 391, etc.), so
``build_full_corpus`` over it yields evidence units that retrieval and the
day-1 pipeline can query without any cache.

Documents:
- ``synth-2024.htm``  — FY2024 10-K (Assets 400, Revenues 391, OCF 118, capex 11).
- ``synth-2023.htm``  — FY2023 10-K (distractor document).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent

# 10-K-shaped paragraphs; values match sec_companyfacts_fixture.json.
_SECTIONS = [
    ("Item 1. Business", (
        "<p>Synthetic Fixture Inc. is a diversified technology company. "
        "For the fiscal year ended September 28, 2024, total assets were "
        "$400,000,000,000 and total revenues were $391,000,000,000.</p>",
    )),
    ("Item 5. Market for Registrant's Common Equity", (
        "<p>The Company's common stock trades on a national securities "
        "exchange. Dividends declared were $15,000,000,000 for fiscal 2024.</p>",
    )),
    ("Item 7. Management's Discussion and Analysis", (
        "<p>Operating cash flow for fiscal 2024 was $118,000,000,000. "
        "Capital expenditures (payments to acquire property, plant and "
        "equipment) were $11,000,000,000.</p>",
    )),
    ("Item 8. Financial Statements", (
        "<table><tr><th>Concept</th><th>FY2024</th></tr>"
        "<tr><td>Assets</td><td>400,000,000,000</td></tr>"
        "<tr><td>Revenues</td><td>391,000,000,000</td></tr>"
        "<tr><td>OperatingCashFlow</td><td>118,000,000,000</td></tr>"
        "<tr><td>CapitalExpenditure</td><td>11,000,000,000</td></tr></table>",
    )),
]

_DISTRACTOR_SECTIONS = [
    ("Item 1. Business", (
        "<p>Legacy Fixture Corp. manufactures fixtures. Total assets were "
        "$5,000,000,000 for the fiscal year ended September 30, 2023.</p>",
    )),
    ("Item 7. Management's Discussion and Analysis", (
        "<p>Operating cash flow was $500,000,000. Capital expenditures were "
        "$80,000,000.</p>",
    )),
]


def _doc_html(sections: list[tuple[str, str]]) -> str:
    body = "".join(
        f"<h2>{title}</h2>" + "".join(paras) for title, paras in sections
    )
    return f"<!DOCTYPE html><html><body>{body}</body></html>"


def write_fixture(dir_path: Path | None = None) -> dict[str, str]:
    """Write the fixture HTML files; return {filename: sha256}."""
    out_dir = dir_path or FIXTURE_DIR
    docs = {
        "synth-2024.htm": _doc_html(_SECTIONS),
        "synth-2023.htm": _doc_html(_DISTRACTOR_SECTIONS),
    }
    digests: dict[str, str] = {}
    for name, content in docs.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        digests[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return digests


def fixture_sha256(name: str = "synth-2024.htm") -> str:
    """Stable content hash for the committed fixture (reproducibility)."""
    path = FIXTURE_DIR / name
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    for name, digest in write_fixture().items():
        print(f"{name} sha256={digest[:16]}")
