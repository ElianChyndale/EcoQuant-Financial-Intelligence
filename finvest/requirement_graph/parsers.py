"""FinVEST requirement-graph parsers (M3).

Three parsers per the master plan:
1. ``deterministic_finance_parser`` — finance-ontology rules (no LLM, no
   training; used as a strong deterministic baseline and to bootstrap labels).
2. ``structured_llm_parser`` — LLM producing schema-valid JSON (requires an
   API key; returns None when unavailable so pipelines degrade gracefully).
3. ``trainable_parser`` — a lightweight sequence-to-graph model (scaffold;
   full training is a later milestone).

Graph-quality metrics: node precision/recall, edge precision/recall, period
accuracy, entity accuracy, metric accuracy, operation accuracy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from finvest.benchmark.schemas import RequirementEdge, RequirementGraph, RequirementNode

# Finance-ontology: metric keyword -> concept + requirement type.
_METRIC_ALIASES = {
    "revenue": "Revenues",
    "total revenue": "Revenues",
    "net sales": "Revenues",
    "net income": "NetIncomeLoss",
    "operating cash flow": "NetCashProvidedByUsedInOperatingActivities",
    "ocf": "NetCashProvidedByUsedInOperatingActivities",
    "capital expenditure": "PaymentsToAcquirePropertyPlantAndEquipment",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
    "fcff": "FCFF",
    "free cash flow": "FCFF",
    "total assets": "Assets",
    "total debt": "LongTermDebt",
    "gross profit": "GrossProfit",
    "working capital": "WorkingCapital",
}

_FISCAL_YEAR_RE = re.compile(r"\b(?:fiscal\s+)?(?:fy)?(20\d{2})\b", re.IGNORECASE)
_ENTITY_RE = re.compile(r"\b(AAPL|MSFT|KO|EQIX|JNJ|UPS|Apple|Microsoft|Coca-Cola|Equinix|Johnson)\b", re.IGNORECASE)
_METRIC_RE = re.compile(
    r"|".join(re.escape(alias) for alias in sorted(_METRIC_ALIASES, key=len, reverse=True)),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedGraph:
    graph: RequirementGraph
    score: float  # 0-1 self-assessed confidence (deterministic for the rule parser)


def deterministic_finance_parser(question: str, ticker: str | None = None) -> ParsedGraph:
    """Rule-based parser: entity, metric, fiscal year, FCFF derivation.

    Produces a RequirementGraph with ENTITY/METRIC/PERIOD nodes and, for FCFF,
    the intermediate-value derivation (OCF - Capex).
    """
    nodes: list[RequirementNode] = []
    edges: list[RequirementEdge] = []
    metric_match = _METRIC_RE.search(question)
    metric = metric_match.group(0).lower() if metric_match else None
    concept = _METRIC_ALIASES.get(metric) if metric else None
    year_match = _FISCAL_YEAR_RE.search(question)
    year = year_match.group(1) if year_match else None
    entity = ticker or (_ENTITY_RE.search(question).group(1).upper() if _ENTITY_RE.search(question) else None)

    if entity:
        nodes.append(RequirementNode("entity", "ENTITY", entity))
    if metric:
        nodes.append(RequirementNode("metric", "METRIC", metric))
    if year:
        nodes.append(RequirementNode("period", "PERIOD", f"FY{year}"))
    if concept:
        nodes.append(RequirementNode("concept", "METRIC", concept))

    # FCFF derivation: concept=FCFF -> intermediates OCF, Capex.
    if concept == "FCFF":
        nodes.extend([
            RequirementNode("ocf", "INTERMEDIATE_VALUE", "NetCashProvidedByUsedInOperatingActivities"),
            RequirementNode("capex", "INTERMEDIATE_VALUE", "PaymentsToAcquirePropertyPlantAndEquipment"),
            RequirementNode("operation", "OPERATION", "subtract"),
        ])
        edges.extend([
            RequirementEdge("metric", "ocf", "DERIVES_FROM"),
            RequirementEdge("metric", "capex", "DERIVES_FROM"),
            RequirementEdge("operation", "ocf", "REQUIRES"),
            RequirementEdge("operation", "capex", "REQUIRES"),
        ])

    graph = RequirementGraph(tuple(nodes), tuple(edges))
    graph.validate()
    score = min(1.0, 0.3 + 0.2 * int(entity is not None) + 0.25 * int(metric is not None)
                + 0.25 * int(year is not None))
    return ParsedGraph(graph, score)


def structured_llm_parser(question: str, *, api_key: str | None = None) -> ParsedGraph | None:
    """LLM parser producing schema-valid JSON.

    Returns None when no API key is available (graceful degradation). The LLM
    is never shown gold graphs at test time.
    """
    if not api_key:
        return None
    # Placeholder: wired to an LLM API in a later milestone with schema
    # validation + node/edge precision checks. Not callable without a key.
    raise NotImplementedError("LLM parser requires an API key; not yet wired")


def trainable_parser(question: str) -> ParsedGraph | None:
    """Trainable sequence-to-graph parser (scaffold).

    Full training is a later milestone. Returns None until trained weights
    exist, so pipelines degrade gracefully.
    """
    return None


def graph_quality(
    predicted: RequirementGraph,
    gold: RequirementGraph,
) -> dict[str, float]:
    """Node/edge precision/recall/F1 between predicted and gold graphs."""
    pred_nodes = {n.node_id for n in predicted.nodes}
    gold_nodes = {n.node_id for n in gold.nodes}
    node_tp = len(pred_nodes & gold_nodes)
    node_precision = node_tp / len(pred_nodes) if pred_nodes else 0.0
    node_recall = node_tp / len(gold_nodes) if gold_nodes else 0.0
    node_f1 = 2 * node_precision * node_recall / (node_precision + node_recall) if node_precision + node_recall else 0.0

    pred_edges = {(e.source_id, e.target_id) for e in predicted.edges}
    gold_edges = {(e.source_id, e.target_id) for e in gold.edges}
    edge_tp = len(pred_edges & gold_edges)
    edge_precision = edge_tp / len(pred_edges) if pred_edges else 0.0
    edge_recall = edge_tp / len(gold_edges) if gold_edges else 0.0
    edge_f1 = 2 * edge_precision * edge_recall / (edge_precision + edge_recall) if edge_precision + edge_recall else 0.0

    return {
        "node_precision": node_precision,
        "node_recall": node_recall,
        "node_f1": node_f1,
        "edge_precision": edge_precision,
        "edge_recall": edge_recall,
        "edge_f1": edge_f1,
    }
