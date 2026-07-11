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

    def add_edge(self, source_id: str, target_id: str, relation: Relation) -> None:
        if source_id not in self._nodes:
            raise ValueError(f"source_id does not identify a graph node: {source_id}")
        if target_id not in self._nodes:
            raise ValueError(f"target_id does not identify a graph node: {target_id}")
        try:
            typed_relation = Relation(relation)
        except (TypeError, ValueError) as error:
            raise ValueError(f"relation must be one of {[item.value for item in Relation]}") from error
        edge = Edge(source_id, target_id, typed_relation)
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

    def contradictions_for(self, claim_id: str) -> list[Claim]:
        contradictions: list[Claim] = []
        for edge in self._edges:
            if edge.relation is not Relation.CONTRADICTS:
                continue
            other_id = edge.target_id if edge.source_id == claim_id else edge.source_id
            if edge.source_id != claim_id and edge.target_id != claim_id:
                continue
            other = self._nodes[other_id]
            if isinstance(other, Claim):
                contradictions.append(other)
        return contradictions
