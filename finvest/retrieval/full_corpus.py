"""FinVEST full-corpus retrieval (A1): full 10-K documents -> ranked evidence.

Replaces the E1 gold-page oracle corpus with the full-document corpus. Stages:
1. Document router: which company's 10-K is relevant.
2. Page/unit retriever: BM25 + dense over all evidence units in the relevant
   document(s).

Metrics (A1): Document Recall@k, Unit Recall@k (All-Required-Evidence Recall),
MRR, nDCG, Requirement Coverage (predicted), set precision, redundancy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from finvest.benchmark.schemas import EvidenceItem
from finvest.document_intelligence.html_parser import parse_10k_html


@dataclass(frozen=True)
class FullCorpus:
    """All evidence units across the full 10-K documents."""

    units: tuple[EvidenceItem, ...]
    documents: tuple[str, ...]  # document_ids
    by_document: dict[str, tuple[EvidenceItem, ...]]


def build_full_corpus(cache_dir: Path, corpus_dir: Path | None = None) -> FullCorpus:
    """Parse full 10-K HTML into one corpus of evidence units.

    ``cache_dir`` is the gitignored SEC cache (default). Pass ``corpus_dir``
    to point at a committed fixture directory (e.g. ``finvest/fixtures``) so
    tests run without the cache.
    """
    full_10k = corpus_dir or cache_dir / "sec" / "full_10k"
    units: list[EvidenceItem] = []
    documents: list[str] = []
    for path in sorted(full_10k.glob("*.htm")):
        document_id = path.stem
        parsed = parse_10k_html(
            path,
            document_id=document_id,
            document_version="10-K",
            filing_date=date(2026, 1, 1),  # placeholder; refine from filing metadata
        )
        units.extend(parsed.evidence_units)
        documents.append(document_id)
    by_document = {doc: tuple(u for u in units if u.document_id == doc) for doc in documents}
    return FullCorpus(tuple(units), tuple(documents), by_document)


@dataclass(frozen=True)
class RankedResult:
    evidence_id: str
    document_id: str
    score: float
    rank: int


def _tokenize(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text.lower()).split()


def bm25_retrieve(corpus: FullCorpus, query: str, top_k: int = 20) -> tuple[RankedResult, ...]:
    """BM25 retrieval over the full corpus."""
    from rank_bm25 import BM25Okapi

    texts = [_tokenize(u.text_span or "") for u in corpus.units]
    bm25 = BM25Okapi(texts)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(
        ((scores[i], corpus.units[i]) for i in range(len(corpus.units))),
        key=lambda item: (-item[0], item[1].evidence_id),
    )[:top_k]
    return tuple(
        RankedResult(evidence_id=unit.evidence_id, document_id=unit.document_id,
                     score=score, rank=rank)
        for rank, (score, unit) in enumerate(ranked, start=1)
    )


def dense_retrieve(corpus: FullCorpus, query: str, top_k: int = 20) -> tuple[RankedResult, ...]:
    """Dense bi-encoder retrieval over the full corpus (all-MiniLM-L6-v2).

    Document embeddings are cached to disk keyed by a corpus fingerprint, so a
    170k-record corpus is encoded ONCE and reused across queries/cases (the
    A11 production path would otherwise re-encode on every call).
    """
    import hashlib
    from functools import lru_cache
    from pathlib import Path as _P

    import numpy as _np
    from sklearn.metrics.pairwise import cosine_similarity

    model_dir = _P(__file__).resolve().parents[2] / "research/cache/models/all-MiniLM-L6-v2"

    @lru_cache(maxsize=1)
    def _model():
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(str(model_dir))

    model = _model()
    texts = [u.text_span or "" for u in corpus.units]

    # Embedding cache keyed by content hash of the corpus texts.
    cache_key = hashlib.sha256(
        "\x1f".join(texts).encode("utf-8")
    ).hexdigest()[:24]
    cache_dir = _P(__file__).resolve().parents[2] / "research/cache/embeddings"
    cache_path = cache_dir / f"{cache_key}.npy"
    if cache_path.exists():
        doc_embeddings = _np.load(str(cache_path))
    else:
        doc_embeddings = model.encode(texts, normalize_embeddings=True, batch_size=64)
        cache_dir.mkdir(parents=True, exist_ok=True)
        _np.save(str(cache_path), doc_embeddings)

    query_embedding = model.encode([query], normalize_embeddings=True)
    scores = cosine_similarity(query_embedding, doc_embeddings).ravel()
    ranked = sorted(
        ((scores[i], corpus.units[i]) for i in range(len(corpus.units))),
        key=lambda item: (-item[0], item[1].evidence_id),
    )[:top_k]
    return tuple(
        RankedResult(evidence_id=unit.evidence_id, document_id=unit.document_id,
                     score=score, rank=rank)
        for rank, (score, unit) in enumerate(ranked, start=1)
    )
