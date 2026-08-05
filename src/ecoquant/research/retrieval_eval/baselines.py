"""E1 sparse / dense / hybrid retrieval baselines over a fixed corpus.

Each baseline returns, per question, a tuple of ``RetrievalResult`` (ranked
evidence pages). The six methods are:

- ``bm25`` — Okapi BM25 (rank_bm25).
- ``tfidf`` — TF-IDF cosine similarity (scikit-learn).
- ``lsa`` — TF-IDF + TruncatedSVD latent semantic indexing.
- ``dense`` — all-MiniLM-L6-v2 bi-encoder cosine similarity (locally cached model).
- ``hybrid_rrf`` — reciprocal-rank fusion of BM25 + dense ranks.
- ``long_context`` — full-document query-term overlap.

All methods are deterministic (fixed seed where stochastic), rank at most top_k=5,
and tie-break by evidence_id. The dense model is loaded lazily from the gitignored
``research/cache/models/all-MiniLM-L6-v2`` directory and cached in-process.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from ecoquant.retrieval.base import CorpusRecord, RetrievalResult

TOP_K = 5

# Absolute path to the locally cached dense model (gitignored). Falls back to the
# sentence-transformers short name if the local cache is absent.
_MODEL_DIR = Path(__file__).resolve().parents[4] / "research" / "cache" / "models" / "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _dense_model():
    from sentence_transformers import SentenceTransformer

    if _MODEL_DIR.exists():
        return SentenceTransformer(str(_MODEL_DIR))
    # Fallback: let sentence-transformers resolve the model name (may download).
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def _tokenize(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text.lower()).split()


def _run_bm25(corpus: Sequence[CorpusRecord], questions: Sequence[object]) -> dict[str, tuple[RetrievalResult, ...]]:
    from rank_bm25 import BM25Okapi

    tokenized_corpus = [_tokenize(record.text) for record in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    by_question: dict[str, tuple[RetrievalResult, ...]] = {}
    for question in questions:
        query = _tokenize(question.query)
        scores = bm25.get_scores(query)
        by_question[question.question_id] = _rank(corpus, scores, "bm25", question.question_id)
    return by_question


def _run_tfidf(corpus: Sequence[CorpusRecord], questions: Sequence[object]) -> dict[str, tuple[RetrievalResult, ...]]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    texts = [record.text for record in corpus]
    vectorizer = TfidfVectorizer(tokenizer=_tokenize, lowercase=True, sublinear_tf=True)
    doc_matrix = vectorizer.fit_transform(texts)
    by_question: dict[str, tuple[RetrievalResult, ...]] = {}
    for question in questions:
        query_vec = vectorizer.transform([question.query])
        scores = cosine_similarity(query_vec, doc_matrix).ravel()
        by_question[question.question_id] = _rank(corpus, scores, "tfidf", question.question_id)
    return by_question


def _run_lsa(corpus: Sequence[CorpusRecord], questions: Sequence[object]) -> dict[str, tuple[RetrievalResult, ...]]:
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import Normalizer

    texts = [record.text for record in corpus]
    vectorizer = TfidfVectorizer(tokenizer=_tokenize, lowercase=True, sublinear_tf=True)
    doc_matrix = vectorizer.fit_transform(texts)
    n_features = doc_matrix.shape[1]
    n_components = min(128, len(texts) - 1, n_features - 1)
    if n_components < 1:
        n_components = 1
    svd = TruncatedSVD(n_components=n_components, random_state=20260806)
    lsa = make_pipeline(svd, Normalizer(copy=False))
    doc_matrix = lsa.fit_transform(doc_matrix)
    by_question: dict[str, tuple[RetrievalResult, ...]] = {}
    for question in questions:
        query_vec = lsa.transform(vectorizer.transform([question.query]))
        scores = cosine_similarity(query_vec, doc_matrix).ravel()
        by_question[question.question_id] = _rank(corpus, scores, "lsa", question.question_id)
    return by_question


def _run_dense(corpus: Sequence[CorpusRecord], questions: Sequence[object]) -> dict[str, tuple[RetrievalResult, ...]]:
    from sklearn.metrics.pairwise import cosine_similarity

    model = _dense_model()
    doc_embeddings = model.encode([record.text for record in corpus], normalize_embeddings=True)
    by_question: dict[str, tuple[RetrievalResult, ...]] = {}
    for question in questions:
        query_embedding = model.encode([question.query], normalize_embeddings=True)
        scores = cosine_similarity(query_embedding, doc_embeddings).ravel()
        by_question[question.question_id] = _rank(corpus, scores, "dense", question.question_id)
    return by_question


def _run_hybrid_rrf(
    corpus: Sequence[CorpusRecord], questions: Sequence[object]
) -> dict[str, tuple[RetrievalResult, ...]]:
    """Reciprocal-rank fusion of BM25 + dense ranks (k=60, the standard RRF constant)."""
    bm25_ranks = _run_bm25(corpus, questions)
    dense_ranks = _run_dense(corpus, questions)
    by_question: dict[str, tuple[RetrievalResult, ...]] = {}
    for question in questions:
        qid = question.question_id
        rrf_scores: dict[str, float] = {}
        for source in (bm25_ranks[qid], dense_ranks[qid]):
            for rank, result in enumerate(source, start=1):
                rrf_scores[result.evidence_id] = rrf_scores.get(result.evidence_id, 0.0) + 1.0 / (60 + rank)
        ranked_ids = sorted(rrf_scores, key=lambda eid: (-rrf_scores[eid], eid))
        results = tuple(
            RetrievalResult(
                method="hybrid_rrf", question_id=qid, evidence_id=eid, rank=rank,
                score=rrf_scores[eid], valid_time_match=True, verification_status="unverified",
            )
            for rank, eid in enumerate(ranked_ids[:TOP_K], start=1)
        )
        by_question[qid] = results
    return by_question


def _run_long_context(
    corpus: Sequence[CorpusRecord], questions: Sequence[object]
) -> dict[str, tuple[RetrievalResult, ...]]:
    """Full-document baseline: score = query-term overlap over the whole document."""
    by_question: dict[str, tuple[RetrievalResult, ...]] = {}
    for question in questions:
        query_terms = set(_tokenize(question.query))
        scores = []
        for record in corpus:
            doc_terms = set(_tokenize(record.text))
            overlap = len(query_terms & doc_terms)
            norm = len(query_terms) if query_terms else 0.0
            scores.append((overlap / norm if norm else 0.0, record))
        ranked = sorted(scores, key=lambda item: (-item[0], item[1].evidence_id))[:TOP_K]
        results = tuple(
            RetrievalResult(
                method="long_context", question_id=question.question_id,
                evidence_id=record.evidence_id, rank=rank, score=score,
                valid_time_match=True, verification_status="unverified",
            )
            for rank, (score, record) in enumerate(ranked, start=1)
        )
        by_question[question.question_id] = results
    return by_question


def _rank(
    corpus: Sequence[CorpusRecord],
    scores: Sequence[float],
    method: str,
    question_id: str,
) -> tuple[RetrievalResult, ...]:
    """Rank corpus records by descending score, deterministic evidence_id tie-break."""
    indexed = sorted(
        ((float(scores[i]), record) for i, record in enumerate(corpus)),
        key=lambda item: (-item[0], item[1].evidence_id),
    )[:TOP_K]
    return tuple(
        RetrievalResult(
            method=method, question_id=question_id, evidence_id=record.evidence_id,
            rank=rank, score=score, valid_time_match=True, verification_status="unverified",
        )
        for rank, (score, record) in enumerate(indexed, start=1)
    )


def run_baselines(
    corpus: Sequence[CorpusRecord],
    queries: Sequence[object],
) -> dict[str, dict[str, tuple[RetrievalResult, ...]]]:
    """Run all E1 baselines over the corpus and return per-method per-question results.

    Args:
        corpus: the retrieval corpus (evidence pages).
        queries: sequence of query views exposing ``.question_id``, ``.query``, ``.issuer``
            (the dataset bundle's ``PublicQueryCase`` records fit this contract).

    Returns:
        Mapping of method name -> {question_id: tuple[RetrievalResult, ...]}.
    """
    return {
        "bm25": _run_bm25(corpus, queries),
        "tfidf": _run_tfidf(corpus, queries),
        "lsa": _run_lsa(corpus, queries),
        "dense": _run_dense(corpus, queries),
        "hybrid_rrf": _run_hybrid_rrf(corpus, queries),
        "long_context": _run_long_context(corpus, queries),
    }
