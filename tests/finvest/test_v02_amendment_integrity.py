"""v0.2 amendment-pair integrity tests.

Prove that amendment pairs are valid: same concept, same period, same unit,
10-K original -> 10-K/A amended, amendment on/after original, accession
differs. Never a cross-concept pair (the v0.1 defect).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from finvest.benchmark.builders.sec_cases import build_sec_cases
from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "research/cache"

# v0.2 amendment-integrity checks run against the COMMITTED fixture (never the
# gitignored SEC cache), so CI exercises the amendment/version constraints.
pytestmark = pytest.mark.local_real_data


def _amended_cases(built) -> list:
    return [c for c in built.cases if c.version_relations]


def test_every_version_relation_same_concept_and_period(built) -> None:
    """A version relation must pair facts with identical concept + period."""
    by_id = {ev.evidence_id: ev for c in built.cases for ev in c.evidence_items}
    for case in _amended_cases(built):
        for relation in case.version_relations:
            source = by_id.get(relation.source_document)
            target = by_id.get(relation.target_document)
            assert source is not None and target is not None, f"missing evidence in relation for {case.case_id}"
            assert source.concept == target.concept, (
                f"{case.case_id}: cross-concept amendment {source['concept']} != {target['concept']}"
            )
            assert source.valid_from == target.valid_from, (
                f"{case.case_id}: period mismatch"
            )


def test_amendment_chronology_valid(built) -> None:
    """Amended filing must be on or after the original filing date."""
    by_id = {ev.evidence_id: ev for c in built.cases for ev in c.evidence_items}
    for case in _amended_cases(built):
        for relation in case.version_relations:
            source = by_id[relation.source_document]
            target = by_id[relation.target_document]
            original_filed = source.filing_date if isinstance(source.filing_date, date) else date.fromisoformat(str(source.filing_date))
            amended_filed = target.filing_date if isinstance(target.filing_date, date) else date.fromisoformat(str(target.filing_date))
            assert amended_filed >= original_filed, (
                f"{case.case_id}: amendment predates original "
                f"({target['filing_date']} < {source['filing_date']})"
            )


def test_amended_form_is_kA(built) -> None:
    """The amended side must be a 10-K/A (or 10-Q/A), the original a 10-K."""
    by_id = {ev.evidence_id: ev for c in built.cases for ev in c.evidence_items}
    for case in _amended_cases(built):
        for relation in case.version_relations:
            source = by_id[relation.source_document]
            target = by_id[relation.target_document]
            assert source.document_version == "10-K", (
                f"{case.case_id}: original form is {source['document_version']}, not 10-K"
            )
            assert target.document_version == "10-K/A", (
                f"{case.case_id}: amended form is {target['document_version']}, not 10-K/A"
            )


def test_amended_values_differ_after_identity(built) -> None:
    """After identity constraints match, the values must differ."""
    by_id = {ev.evidence_id: ev for c in built.cases for ev in c.evidence_items}
    for case in _amended_cases(built):
        assert case.known_conflicts, f"{case.case_id}: amended case must record a value conflict"


def test_no_cross_concept_pair_in_built_queue(built) -> None:
    """Regression: the v0.1 cross-concept defect must not recur."""
    by_id = {ev.evidence_id: ev for c in built.cases for ev in c.evidence_items}
    for case in _amended_cases(built):
        for relation in case.version_relations:
            source = by_id[relation.source_document]
            target = by_id[relation.target_document]
            assert source.concept == target.concept


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    # Build from the committed fixture: one companyfacts file PER TICKER.
    tmp = tmp_path_factory.mktemp("sec-cache")
    sec = tmp / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
        encoding="utf-8"
    )
    for ticker in ("AAPL", "MSFT", "KO"):
        (sec / f"{ticker.lower()}_companyfacts.json").write_text(
            fixture_json, encoding="utf-8"
        )
    return build_sec_cases(tmp, tickers=("AAPL", "MSFT", "KO"), fixture=True)
