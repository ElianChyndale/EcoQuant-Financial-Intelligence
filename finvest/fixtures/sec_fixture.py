"""Committed synthetic SEC fixture builder (Phase 3).

Unit/workflow tests must depend ONLY on this committed fixture — never the
gitignored SEC cache. The fixture exercises every identity case the resolver
and builder must handle:

- a normal 10-K fact,
- a correct 10-K/A amendment pair (same concept/period/unit),
- a cross-concept error pair (the v0.1 defect),
- a future filing (filed after the source cutoff),
- a wrong-unit fact,
- a duplicate identity (two facts with the same concept/end/form/unit),
- a real duration period (start != end),
- a negative candidate (no matching fact).

Generates a companyfacts-shaped JSON payload that the SecFact adapter can
parse, plus a manifest of synthetic source hashes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent


def _fact(concept: str, val: float, *, start: str, end: str, filed: str,
          form: str, accn: str, unit: str = "USD", fy: int | None = None,
          fp: str | None = None, frame: str | None = None) -> dict:
    return {
        "val": val, "unit": unit, "start": start, "end": end,
        "filed": filed, "form": form, "accn": accn, "fy": fy, "fp": fp,
        "frame": frame,
    }


def build_companyfacts_payload() -> dict:
    """Return a synthetic companyfacts JSON (AAPL-shaped, all edge cases)."""
    facts = {
        # Normal 10-K instant fact (assets at a period end).
        "Assets": {
            "label": "Assets", "units": {"USD": [
                _fact("Assets", 400_000_000_000,
                      start=None, end="2024-09-28", filed="2024-11-01",
                      form="10-K", accn="0000320193-24-000123", fy=2024, fp="FY"),
            ]},
        },
        # Normal duration-period fact (revenue for FY2024).
        "Revenues": {
            "label": "Revenues", "units": {"USD": [
                _fact("Revenues", 391_000_000_000,
                      start="2023-10-01", end="2024-09-28", filed="2024-11-01",
                      form="10-K", accn="0000320193-24-000123", fy=2024, fp="FY"),
            ]},
        },
        # FCFF-style derived case inputs (OCF - capex), FY2024 duration facts.
        "NetCashProvidedByUsedInOperatingActivities": {
            "label": "NetCashProvidedByUsedInOperatingActivities", "units": {"USD": [
                _fact(FCFF_OCF_CONCEPT, 118_000_000_000,
                      start="2023-10-01", end="2024-09-28", filed="2024-11-01",
                      form="10-K", accn="0000320193-24-000123", fy=2024, fp="FY"),
            ]},
        },
        "PaymentsToAcquirePropertyPlantAndEquipment": {
            "label": "PaymentsToAcquirePropertyPlantAndEquipment", "units": {"USD": [
                _fact(FCFF_CAPEX_CONCEPT, 11_000_000_000,
                      start="2023-10-01", end="2024-09-28", filed="2024-11-01",
                      form="10-K", accn="0000320193-24-000123", fy=2024, fp="FY"),
            ]},
        },
        # Correct amendment pair: AccruedLiabilitiesCurrent restated by 10-K/A.
        "AccruedLiabilitiesCurrent": {
            "label": "AccruedLiabilitiesCurrent", "units": {"USD": [
                _fact("AccruedLiabilitiesCurrent", 3_376_000_000,
                      start=None, end="2008-09-27", filed="2009-10-27",
                      form="10-K", accn="0000320193-09-000111", fy=2009, fp="FY"),
                _fact("AccruedLiabilitiesCurrent", 3_852_000_000,
                      start=None, end="2008-09-27", filed="2010-10-27",
                      form="10-K/A", accn="0000320193-10-000222", fy=2009, fp="FY"),
            ]},
        },
        # CROSS-CONCEPT error pair (v0.1 defect): different concept for the
        # same period as 10-K/A.
        "EntityPublicFloat": {
            "label": "EntityPublicFloat", "units": {"USD": [
                _fact("EntityPublicFloat", 100_000_000,
                      start=None, end="2008-09-27", filed="2010-01-25",
                      form="10-K/A", accn="0000320193-10-000033", fy=2009, fp="FY"),
            ]},
        },
        # Future filing: filed after the source cutoff it must not be used at.
        "FutureExpense": {
            "label": "FutureExpense", "units": {"USD": [
                _fact("FutureExpense", 50_000_000,
                      start="2024-01-01", end="2024-09-28", filed="2026-05-01",
                      form="10-K", accn="0000320193-26-000999", fy=2026, fp="FY"),
            ]},
        },
        # Wrong-unit fact: revenue reported in EUR (not USD).
        "RevenueEur": {
            "label": "RevenueEur", "units": {"EUR": [
                _fact("RevenueEur", 360_000_000_000,
                      start="2023-10-01", end="2024-09-28", filed="2024-11-01",
                      form="10-K", accn="0000320193-24-000124", fy=2024, fp="FY", unit="EUR"),
            ]},
        },
        # Revenue in a different fiscal year (FY2023) so the insufficient
        # builder has a reported-in-other-years metric for a 2024 gap.
        "RevenueOld": {
            "label": "RevenueOld", "units": {"USD": [
                _fact("RevenueOld", 365_000_000_000,
                      start="2022-09-29", end="2023-09-30", filed="2023-11-02",
                      form="10-K", accn="0000320193-23-000313", fy=2023, fp="FY"),
            ]},
        },
        # Duplicate identity: two facts same concept/end/form/unit (ambiguous).
        "DuplicateMetric": {
            "label": "DuplicateMetric", "units": {"USD": [
                _fact("DuplicateMetric", 1_000_000_000,
                      start=None, end="2024-09-28", filed="2024-11-01",
                      form="10-K", accn="0000320193-24-000201", fy=2024, fp="FY"),
                _fact("DuplicateMetric", 2_000_000_000,
                      start=None, end="2024-09-28", filed="2024-11-01",
                      form="10-K", accn="0000320193-24-000202", fy=2024, fp="FY"),
            ]},
        },
    }
    return {
        "cik": "0000320193",
        "entityName": "Synthetic Fixture Inc.",
        "facts": {"us-gaap": facts},
    }


# Concepts for the FCFF-style derived case (OCF - capex). The synthetic fixture
# needs a duration-period 10-K fact per concept so _fcff_case can build.
FCFF_OCF_CONCEPT = "NetCashProvidedByUsedInOperatingActivities"
FCFF_CAPEX_CONCEPT = "PaymentsToAcquirePropertyPlantAndEquipment"


def write_fixture(dir_path: Path | None = None) -> tuple[Path, str]:
    """Write the synthetic companyfacts fixture + return (path, sha256)."""
    out_dir = dir_path or FIXTURE_DIR
    payload = build_companyfacts_payload()
    content = json.dumps(payload, indent=2, sort_keys=True)
    path = out_dir / "sec_companyfacts_fixture.json"
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return path, digest


def load_fixture() -> dict:
    path = FIXTURE_DIR / "sec_companyfacts_fixture.json"
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    path, digest = write_fixture()
    print(f"wrote {path} sha256={digest[:16]}")
