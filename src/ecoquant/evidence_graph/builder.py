from collections.abc import Iterable
from datetime import date

from ecoquant.document_intelligence.schema import EvidenceSpanV1

from .graph import Relation, TemporalEvidenceGraph
from .models import Claim, Document, Metric


def build_graph(
    evidence_spans: Iterable[EvidenceSpanV1] | Iterable[Claim] = (),
    claims: Iterable[Claim] = (),
    metrics: Iterable[Metric] = (),
) -> TemporalEvidenceGraph:
    """Build a deterministic temporal graph from ordered evidence and claims.

    A claim can supersede another claim only when both are checked, the newer
    claim names its predecessor explicitly, and they address the same subject
    and metric. A later claim that differs without that explicit relationship
    contradicts every earlier checked claim for the same subject and metric.
    """
    evidence_items = list(evidence_spans)
    ordered_claims = list(claims)
    if not ordered_claims and all(isinstance(item, Claim) for item in evidence_items):
        ordered_claims = evidence_items
        evidence_items = []
    if not all(isinstance(item, EvidenceSpanV1) for item in evidence_items):
        raise TypeError("evidence_spans must contain EvidenceSpanV1 records")

    graph = TemporalEvidenceGraph()
    for metric in metrics:
        graph.add_node(metric)

    for evidence in evidence_items:
        document = Document(
            id=evidence.document_id,
            issuer_id=evidence.issuer_id,
            valid_time=_report_period_end(evidence.report_period),
            source_time=evidence.source_date,
        )
        try:
            graph.add_node(document)
        except ValueError:
            existing = graph.node(document.id)
            if not isinstance(existing, Document) or existing.issuer_id != document.issuer_id:
                raise
        graph.add_evidence(evidence.issuer_id, _report_period_end(evidence.report_period), evidence)

    claim_by_id = {claim.id: claim for claim in ordered_claims}
    if len(claim_by_id) != len(ordered_claims):
        raise ValueError("claim ids must be unique")
    for claim in ordered_claims:
        if claim.supersedes_id is not None and claim.supersedes_id not in claim_by_id:
            raise ValueError(f"supersedes_id does not identify a claim: {claim.supersedes_id}")
        graph.add_node(claim)

    for position, claim in enumerate(ordered_claims):
        if not claim.checked:
            continue
        for prior in ordered_claims[:position]:
            if not prior.checked or not _is_newer(claim, prior):
                continue
            if claim.subject_id != prior.subject_id or claim.metric_id != prior.metric_id:
                continue
            if claim.supersedes_id == prior.id:
                graph.add_edge(claim.id, prior.id, Relation.SUPERSEDES)
            elif claim.value != prior.value or claim.provenance != prior.provenance:
                graph.add_edge(claim.id, prior.id, Relation.CONTRADICTS)
    return graph


def _is_newer(candidate: Claim, prior: Claim) -> bool:
    return (candidate.valid_time, candidate.source_time) > (prior.valid_time, prior.source_time)


def _report_period_end(report_period: str) -> date:
    try:
        return date.fromisoformat(report_period)
    except ValueError:
        pass
    if len(report_period) == 4 and report_period.isdigit():
        return date(int(report_period), 12, 31)
    raise ValueError("report_period must be an ISO date or four-digit year")
