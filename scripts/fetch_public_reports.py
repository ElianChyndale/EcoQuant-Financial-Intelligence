#!/usr/bin/env python3
"""Fetch a frozen public-report manifest into an external, verified cache."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_HOSTS = frozenset({"aib.ie", "www.aib.ie", "cdn.esb.ie", "enel.com", "www.enel.com", "kfw.de", "www.kfw.de"})
SAFE_SOURCE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _require_official_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError(f"refusing non-official HTTPS source: {url}")


def _require_safe_source_id(source_id: str) -> None:
    if not SAFE_SOURCE_ID.fullmatch(source_id):
        raise ValueError(f"unsafe source_id for cache filename: {source_id!r}")


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _require_official_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fetch_report(row: dict[str, str], cache_dir: Path) -> Path:
    source_id, url, expected = row["source_id"], row["official_url"], row["sha256"]
    _require_safe_source_id(source_id)
    _require_official_https(url)
    target = cache_dir / f"{source_id}.pdf"
    if target.exists():
        actual = _sha256(target)
        if actual != expected:
            raise ValueError(f"cache hash mismatch for {source_id}: {actual} != {expected}")
        return target

    fd, temporary_name = tempfile.mkstemp(prefix=f".{source_id}.", suffix=".part", dir=cache_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as output:
            request = Request(url, headers={"User-Agent": "EcoQuant-public-corpus-fetcher/1.0"})
            with build_opener(OfficialRedirects()).open(request, timeout=120) as response:
                _require_official_https(response.url)
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(chunk)
        if temporary.read_bytes()[:5] != b"%PDF-":
            raise ValueError(f"download is not a PDF for {source_id}")
        actual = _sha256(temporary)
        if actual != expected:
            raise ValueError(f"download hash mismatch for {source_id}: {actual} != {expected}")
        temporary.replace(target)
        return target
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPOSITORY_ROOT / "research/sources/source_manifest.csv")
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "ecoquant-public-report-cache")
    args = parser.parse_args()
    cache_dir = args.cache_dir.expanduser().resolve()
    if _is_inside(cache_dir, REPOSITORY_ROOT):
        parser.error("--cache-dir must be outside the repository; raw PDFs are never stored in tracked paths")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for row in load_manifest(args.manifest):
        print(fetch_report(row, cache_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
