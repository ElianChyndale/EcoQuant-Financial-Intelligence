"""Dataset bundle contracts separating public query cases from gold records.

These types are the E0 boundary: a system may consume ``PublicQueryCase``
records; only an evaluator may access ``GoldEvaluationRecord`` records. The
``DatasetBundle`` keeps the two sets strictly separated and carries a frozen
manifest so every downstream result is traceable to a dataset hash and adapter
version.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PublicQueryCase:
    """What a system sees: query + issuer + periods + temporal cutoff. No gold."""

    question_id: str
    question_type: str
    issuer: str
    query: str
    periods: tuple[str, ...]
    valid_at: date
    source_cutoff: date | None = None


@dataclass(frozen=True)
class GoldEvaluationRecord:
    """What an evaluator sees: the ground truth for one question. Never in prompts."""

    question_id: str
    question_type: str
    issuer: str
    gold_source_ids: tuple[str, ...]
    gold_page_ids: tuple[str, ...]
    gold_block_ids: tuple[str, ...]
    gold_answer: str
    label_provenance: str


@dataclass(frozen=True)
class DatasetBundle:
    dataset_id: str
    public_cases: tuple[PublicQueryCase, ...]
    gold_records: tuple[GoldEvaluationRecord, ...]
    manifest: dict[str, object]
