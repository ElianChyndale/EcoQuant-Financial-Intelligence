"""Shared pytest fixtures for FinVEST tests.

``local_real_data`` tests depend on the gitignored SEC cache. They skip
cleanly when the cache is absent (e.g. CI), so the suite never crashes on a
missing cache.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEC_CACHE = ROOT / "research/cache/sec"


def _cache_present() -> bool:
    """True when the gitignored SEC cache has at least one companyfacts file."""
    if not SEC_CACHE.exists():
        return False
    return any(SEC_CACHE.glob("*_companyfacts.json"))


@pytest.fixture(autouse=True)
def _skip_local_real_data_without_cache(request: pytest.FixtureRequest) -> None:
    """Auto-skip any test marked local_real_data when the SEC cache is absent."""
    if request.node.get_closest_marker("local_real_data") and not _cache_present():
        pytest.skip("gitignored SEC cache absent — local-real-data test skipped (CI-safe)")
