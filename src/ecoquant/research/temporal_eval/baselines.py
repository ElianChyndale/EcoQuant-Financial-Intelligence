"""E3 temporal retrieval baselines + contradiction detection.

- ``run_b1_bm25``: plain BM25 over concept text, no temporal filtering.
- ``run_b2_hybrid``: BM25 + dense-style overlap hybrid (concept + form + frame).
- ``run_b3_source_time_filter``: B1 + drop facts filed after ``source_cutoff``
  (no future information).
- ``run_b4_valid_time_filter``: B1 + drop facts with ``end`` after ``valid_at``
  (no future valid periods).
- ``run_b5_temporal_contradiction``: B4 + contradiction detection — when the
  same (concept, end) has multiple values across filed dates, prefer the latest
  filed and mark the earlier one as a contradiction.

Each returns {question_id: tuple[SecFact, ...]} ranked by relevance.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from .questions import TemporalQuestion
from .sec_adapter import SecBundle, SecFact

TOP_K = 5


def _tokenize(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text.lower()).split()


def _fact_text(fact: SecFact) -> str:
    """Retrievable text for a fact: concept + form + frame (temporal hints)."""
    parts = [fact.concept, fact.form, fact.frame or "", str(fact.end.year)]
    return " ".join(parts)


def _facts_for_ticker(bundle: SecBundle, ticker: str) -> list[SecFact]:
    return [fact for fact in bundle.facts if fact.ticker == ticker]


def _ranked(
    facts: list[SecFact],
    question: TemporalQuestion,
    method: str,
) -> tuple[SecFact, ...]:
    """BM25-rank the facts for a question; tie-break by fact_id."""
    corpus = [_fact_text(fact) for fact in facts]
    if not corpus:
        return ()
    bm25 = BM25Okapi([_tokenize(text) for text in corpus])
    scores = bm25.get_scores(_tokenize(question.question))
    ranked = sorted(
        ((scores[i], facts[i]) for i in range(len(facts))),
        key=lambda item: (-item[0], item[1].fact_id),
    )[:TOP_K]
    return tuple(fact for _, fact in ranked)


def run_b1_bm25(bundle: SecBundle, questions: Sequence[TemporalQuestion]) -> dict[str, tuple[SecFact, ...]]:
    return {
        question.question_id: _ranked(_facts_for_ticker(bundle, question.ticker), question, "b1")
        for question in questions
    }


@lru_cache(maxsize=1)
def _dense_model():
    """Cached all-MiniLM-L6-v2 bi-encoder (reused from E1; local cache)."""
    from sentence_transformers import SentenceTransformer

    model_dir = Path(__file__).resolve().parents[4] / "research" / "cache" / "models" / "all-MiniLM-L6-v2"
    if model_dir.exists():
        return SentenceTransformer(str(model_dir))
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def run_b2_hybrid(bundle: SecBundle, questions: Sequence[TemporalQuestion]) -> dict[str, tuple[SecFact, ...]]:
    """Hybrid: BM25 + dense bi-encoder cosine (real semantic signal)."""
    from sklearn.metrics.pairwise import cosine_similarity

    model = _dense_model()
    output: dict[str, tuple[SecFact, ...]] = {}
    for question in questions:
        facts = _facts_for_ticker(bundle, question.ticker)
        corpus = [_fact_text(fact) for fact in facts]
        if not corpus:
            output[question.question_id] = ()
            continue
        bm25 = BM25Okapi([_tokenize(text) for text in corpus])
        scores = bm25.get_scores(_tokenize(question.question))
        doc_embeddings = model.encode(corpus, normalize_embeddings=True)
        query_embedding = model.encode([question.question], normalize_embeddings=True)
        dense_scores = cosine_similarity(query_embedding, doc_embeddings).ravel()
        # RRF-style fusion of BM25 and dense ranks.
        bm25_rank = _rank_indices(scores)
        dense_rank = _rank_indices(dense_scores)
        fused = {
            i: 1.0 / (60 + bm25_rank[i]) + 1.0 / (60 + dense_rank[i])
            for i in range(len(facts))
        }
        ranked = sorted(
            ((fused[i], facts[i]) for i in range(len(facts))),
            key=lambda item: (-item[0], item[1].fact_id),
        )[:TOP_K]
        output[question.question_id] = tuple(fact for _, fact in ranked)
    return output


def _rank_indices(scores: Sequence[float]) -> dict[int, int]:
    """Rank indices by descending score (1-based), ties broken by index."""
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    return {index: rank for rank, index in enumerate(order, start=1)}


def run_b3_source_time_filter(bundle: SecBundle, questions: Sequence[TemporalQuestion]) -> dict[str, tuple[SecFact, ...]]:
    """B1 + no facts filed after source_cutoff (no future information)."""
    output: dict[str, tuple[SecFact, ...]] = {}
    for question in questions:
        facts = [
            fact for fact in _facts_for_ticker(bundle, question.ticker)
            if fact.filed <= question.source_cutoff
        ]
        output[question.question_id] = _ranked(facts, question, "b3")
    return output


def run_b4_valid_time_filter(bundle: SecBundle, questions: Sequence[TemporalQuestion]) -> dict[str, tuple[SecFact, ...]]:
    """B1 + no facts with end after valid_at (no future valid periods)."""
    output: dict[str, tuple[SecFact, ...]] = {}
    for question in questions:
        facts = [
            fact for fact in _facts_for_ticker(bundle, question.ticker)
            if fact.end <= question.valid_at
        ]
        output[question.question_id] = _ranked(facts, question, "b4")
    return output


def run_b5_temporal_contradiction(bundle: SecBundle, questions: Sequence[TemporalQuestion]) -> dict[str, tuple[SecFact, ...]]:
    """B4 + contradiction detection: latest-filed value wins; older flagged.

    Returns ranked facts with the *latest valid* fact first when a contradiction
    (same concept+end, multiple filed values) exists. The runner uses this to
    compute contradiction-detection F1.
    """
    output: dict[str, tuple[SecFact, ...]] = {}
    for question in questions:
        facts = [
            fact for fact in _facts_for_ticker(bundle, question.ticker)
            if fact.end <= question.valid_at
        ]
        # Group by (concept, end); keep the latest-filed per group.
        by_key: dict[tuple[str, str], list[SecFact]] = defaultdict(list)
        for fact in facts:
            by_key[(fact.concept, str(fact.end))].append(fact)
        deduped: list[SecFact] = []
        for key, group in by_key.items():
            latest = max(group, key=lambda f: f.filed)
            deduped.append(latest)
        output[question.question_id] = _ranked(deduped, question, "b5")
    return output
