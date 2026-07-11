from datetime import date

import pytest

from ecoquant.document_intelligence.schema import EvidenceSpanV1
from ecoquant.evidence_graph.builder import build_graph
from ecoquant.evidence_graph.graph import Relation, TemporalEvidenceGraph
from ecoquant.evidence_graph.models import Claim


def _claim(
    claim_id: str,
    *,
    valid_time: date,
    value: int,
    provenance: str = "audited-report",
    supersedes_id: str | None = None,
) -> Claim:
    return Claim(
        id=claim_id,
        subject_id="bond-1",
        metric_id="allocation-rate",
        value=value,
        checked=True,
        provenance=provenance,
        valid_time=valid_time,
        source_time=valid_time,
        supersedes_id=supersedes_id,
    )


def _evidence(*, report_period: str, source_date: date) -> EvidenceSpanV1:
    return EvidenceSpanV1(
        schema_version="evidence-span.v1",
        document_id="document-1",
        issuer_id="issuer-1",
        report_period=report_period,
        source_date=source_date,
        page_id="page-1",
        block_id="block-1",
        bbox=(0.0, 0.0, 10.0, 10.0),
        section="Allocation",
        text="Allocation rate was reported.",
        text_hash="0" * 64,
        extraction_confidence=0.9,
        provider="pdf-manager",
        content_hash="1" * 64,
    )


def test_newer_checked_claim_explicitly_supersedes_changed_value() -> None:
    older = _claim("claim-2023", valid_time=date(2023, 12, 31), value=40)
    newer = _claim(
        "claim-2024",
        valid_time=date(2024, 12, 31),
        value=55,
        supersedes_id=older.id,
    )

    graph = build_graph([older, newer])

    assert graph.has_edge(newer.id, older.id, relation=Relation.SUPERSEDES)
    assert graph.node(newer.id).valid_time.year == 2024


def test_later_changed_claim_without_explicit_supersession_contradicts() -> None:
    earlier = _claim("claim-earlier", valid_time=date(2023, 12, 31), value=40)
    later = _claim(
        "claim-later",
        valid_time=date(2024, 12, 31),
        value=55,
    )

    graph = build_graph(claims=[earlier, later])

    assert graph.has_edge(later.id, earlier.id, relation=Relation.CONTRADICTS)
    assert not graph.has_edge(later.id, earlier.id, relation=Relation.SUPERSEDES)
    assert graph.contradictions_for(earlier.id) == [later]


def test_add_edge_rejects_dangling_node_ids() -> None:
    graph = TemporalEvidenceGraph()
    claim = _claim("claim-1", valid_time=date(2024, 1, 1), value=40)
    graph.add_node(claim)

    with pytest.raises(ValueError, match="target_id"):
        graph.add_edge(claim.id, "missing-claim", Relation.SUPPORTS)


def test_evidence_valid_at_filters_by_report_period_for_asset() -> None:
    evidence_2023 = _evidence(report_period="2023", source_date=date(2024, 2, 1))
    evidence_2024 = _evidence(report_period="2024", source_date=date(2025, 2, 1))

    graph = build_graph(evidence_spans=[evidence_2023, evidence_2024])

    assert graph.evidence_valid_at("issuer-1", date(2023, 12, 31)) == [evidence_2023]


def test_document_node_retains_evidence_source_time() -> None:
    source_date = date(2025, 2, 1)
    evidence = _evidence(report_period="2024", source_date=source_date)

    graph = build_graph(evidence_spans=[evidence])

    assert graph.node(evidence.document_id).source_time == source_date
    assert graph.node(evidence.document_id).valid_time == date(2024, 12, 31)


def test_add_edge_rejects_invalid_relation_values() -> None:
    graph = TemporalEvidenceGraph()
    first = _claim("claim-1", valid_time=date(2024, 1, 1), value=40)
    second = _claim("claim-2", valid_time=date(2024, 2, 1), value=40)
    graph.add_node(first)
    graph.add_node(second)

    with pytest.raises(ValueError, match="relation"):
        graph.add_edge(first.id, second.id, "RELATED")  # type: ignore[arg-type]
