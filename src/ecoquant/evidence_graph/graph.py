from dataclasses import dataclass
from datetime import date
from enum import Enum

from ecoquant.document_intelligence.schema import EvidenceSpanV1

from .models import Claim, GraphNode, NODE_TYPES


class Relation(str, Enum):
    ISSUED = "ISSUED"
    CONTAINS = "CONTAINS"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    AFFECTS = "AFFECTS"
    VALID_AT = "VALID_AT"
    SOURCED_AT = "SOURCED_AT"


@dataclass(frozen=True)
class Edge:
    source_id: str
    target_id: str
    relation: Relation
    evaluator_only: bool = False


class TemporalEvidenceGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[Edge] = []
        self._evidence: list[tuple[str, date, EvidenceSpanV1]] = []

    def add_node(self, node: GraphNode) -> None:
        if not isinstance(node, NODE_TYPES):
            raise TypeError("node must be a typed graph node")
        if not node.id:
            raise ValueError("node id must not be empty")
        existing = self._nodes.get(node.id)
        if existing is not None and existing != node:
            raise ValueError(f"node id already exists: {node.id}")
        self._nodes[node.id] = node

    def add_edge(self, source_id: str, target_id: str, relation: Relation, *, evaluator_only: bool = False) -> None:
        if source_id not in self._nodes:
            raise ValueError(f"source_id does not identify a graph node: {source_id}")
        if target_id not in self._nodes:
            raise ValueError(f"target_id does not identify a graph node: {target_id}")
        try:
            typed_relation = Relation(relation)
        except (TypeError, ValueError) as error:
            raise ValueError(f"relation must be one of {[item.value for item in Relation]}") from error
        edge = Edge(source_id, target_id, typed_relation, evaluator_only)
        if edge not in self._edges:
            self._edges.append(edge)

    def add_evidence(self, asset_id: str, valid_time: date, evidence: EvidenceSpanV1) -> None:
        self._evidence.append((asset_id, valid_time, evidence))

    def node(self, node_id: str) -> GraphNode:
        return self._nodes[node_id]

    def has_edge(self, source_id: str, target_id: str, relation: Relation) -> bool:
        try:
            typed_relation = Relation(relation)
        except (TypeError, ValueError):
            return False
        return Edge(source_id, target_id, typed_relation) in self._edges

    def evidence_valid_at(self, asset_id: str, as_of: date) -> list[EvidenceSpanV1]:
        return [
            evidence
            for evidence_asset_id, valid_time, evidence in self._evidence
            if evidence_asset_id == asset_id and valid_time <= as_of
        ]

    def resolve_query_concepts(self, query: str) -> frozenset[str]:
        """Resolve source-visible query terms; no evaluator annotations are read."""
        return frozenset("".join(char if char.isalnum() else " " for char in query.lower()).split())

    def traverse_evidence(self, issuer_id: str, concepts: frozenset[str]) -> list[EvidenceSpanV1]:
        """Traverse issuer-linked source evidence matching resolved concepts."""
        return [
            evidence
            for asset_id, _, evidence in self._evidence
            if asset_id == issuer_id
            and (not concepts or concepts & self.resolve_query_concepts(evidence.text))
        ]

    def candidate_evidence_ids(self, issuer_id: str, query: str) -> frozenset[str]:
        """Static graph traversal: deliberately does not apply valid-time filtering."""
        concepts = self.resolve_query_concepts(query)
        return frozenset(evidence.document_id for evidence in self.traverse_evidence(issuer_id, concepts))

    def temporal_candidate_evidence_ids(self, issuer_id: str, query: str, cutoff: date) -> frozenset[str]:
        """The same traversal boundary, intersected with valid-time evidence."""
        static_ids = self.candidate_evidence_ids(issuer_id, query)
        return frozenset(
            evidence.document_id for evidence in self.evidence_valid_at(issuer_id, cutoff)
            if evidence.document_id in static_ids
        )

    def retrieval_edges(self) -> tuple[Edge, ...]:
        """Only source-derived graph relations are retriever-visible."""
        return tuple(edge for edge in self._edges if not edge.evaluator_only)

    def contradictions_for(self, claim_id: str) -> list[Claim]:
        contradictions: list[Claim] = []
        for edge in self._edges:
            if edge.evaluator_only or edge.relation is not Relation.CONTRADICTS:
                continue
            other_id = edge.target_id if edge.source_id == claim_id else edge.source_id
            if edge.source_id != claim_id and edge.target_id != claim_id:
                continue
            other = self._nodes[other_id]
            if isinstance(other, Claim):
                contradictions.append(other)
        return contradictions
