"""Fetch full SEC 10-K HTML documents for benchmark companies (A1 enabler).

Rate-limited (SEC requires ≤10 req/s; we use ~1/s), resume-safe (skips
already-fetched), and cache-only (gitignored). Uses the submissions API to
find the latest 10-K accession + primary document.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

USER_AGENT = "EcoQuant FinVEST research elian@example.com"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"

# (ticker, CIK zero-padded)
COMPANIES = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "KO": "0000021344",
    "EQIX": "0001101239",
    "JNJ": "0000200406",
    "UPS": "0001090727",
}


class _SecRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with build_opener(_SecRedirect()).open(request, timeout=60) as response:
        return response.read()


def latest_10k_doc(cik: str, ticker: str) -> tuple[str, str, str]:
    """Return (accession, largest_htm_url, filing_date) for the latest 10-K.

    Selects the LARGEST .htm file in the filing: the primary document is often
    a cover page only (small), while the real 10-K body is the largest htm.
    """
    submissions = json.loads(_fetch(SEC_SUBMISSIONS.format(cik=cik)))
    recent = submissions["filings"]["recent"]
    for accession, form, filed in zip(
        recent["accessionNumber"], recent["form"], recent["filingDate"]
    ):
        if form == "10-K":
            accession_clean = accession.replace("-", "")
            index = _fetch(f"{SEC_ARCHIVE.format(cik=cik, accession=accession_clean)}index.json")
            index_data = json.loads(index)
            items = index_data.get("directory", {}).get("item", [])
            htm_items = [
                item for item in items
                if item["name"].lower().endswith(".htm") and item["name"].lower() != "index.htm"
            ]
            if not htm_items:
                continue
            # Pick the largest htm = the full 10-K body. Sizes in the JSON API
            # may be strings; parse defensively.
            def _size(item: dict[str, object]) -> int:
                try:
                    return int(item.get("size", 0))
                except (TypeError, ValueError):
                    return 0
            largest = max(htm_items, key=_size)
            url = f"{SEC_ARCHIVE.format(cik=cik, accession=accession_clean)}{largest['name']}"
            return accession_clean, url, filed
    raise RuntimeError(f"no 10-K found for {ticker}")


def fetch_full_10ks(cache_dir: Path, tickers: tuple[str, ...] | None = None) -> dict[str, str]:
    """Fetch latest full 10-K HTML for each company into cache/sec/full_10k/.

    Returns {ticker: local_path}. Resume-safe: skips existing files.
    """
    out_dir = cache_dir / "sec" / "full_10k"
    out_dir.mkdir(parents=True, exist_ok=True)
    tickers = tickers or tuple(COMPANIES)
    results: dict[str, str] = {}
    for ticker in tickers:
        cik = COMPANIES[ticker]
        target = out_dir / f"{ticker.lower()}-10k.htm"
        if target.exists():
            results[ticker] = str(target)
            continue
        try:
            accession, url, filed = latest_10k_doc(cik, ticker)
            content = _fetch(url)
            target.write_bytes(content)
            results[ticker] = str(target)
            print(f"{ticker}: {len(content)} bytes ({filed})")
        except Exception as exc:  # noqa: BLE001 — report per-company failure
            print(f"{ticker}: FAILED ({exc})")
        time.sleep(1.1)  # SEC rate limit
    return results


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    fetch_full_10ks(root / "research/cache", tickers=sys.argv[1:] or None)
