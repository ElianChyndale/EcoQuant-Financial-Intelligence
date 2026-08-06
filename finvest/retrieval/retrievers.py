"""FinVEST retrieval layer (Phase 3): R1-R4 retrievers over the leak-free corpus.

Reuses existing implementations where possible (no second retrieval stack):
  R1 BM25  — reuses finvest/retrieval/full_corpus.py::bm25_retrieve
  R2 dense — reuses finvest/retrieval/full_corpus.py::dense_retrieve
  R3 RRF   — NEW: Reciprocal Rank Fusion over BM25 + dense top-200
  R4 concept-temporal — NEW: concept-graph proxy ranked by natural-language
             term overlap with the public concept dictionary, filtered to
             filing_date <= source_cutoff.

Gold-blind contract for R4 (user feedback): the concept retriever must NOT read
the case payload's gold concept / selected evidence / requirement graph /
calculation program. It uses ONLY:
  - the natural-language question,
  - the issuer,
  - the target period,
  - a public, versioned concept dictionary (CONCEPT_DICTIONARY below).

The dictionary is built BEFORE evaluation labels and is not tuned per case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from finvest.retrieval.full_corpus import FullCorpus, RankedResult

RRF_CONST = 60.0
RRF_TOP_N = 200

# Public, versioned concept dictionary: natural-language terms -> XBRL concepts.
# This is a standalone mapping (finance vocabulary), NOT derived from any
# benchmark case or gold label. Extending it must not be case-specific.
CONCEPT_DICTIONARY: dict[str, tuple[str, ...]] = {
    "operating cash flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "net cash from operating": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital expenditure": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "property plant equipment payments": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "total assets": ("Assets",),
    "assets": ("Assets",),
    "total liabilities": ("Liabilities",),
    "liabilities": ("Liabilities",),
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    "revenues": ("Revenues",),
    "net income": ("NetIncomeLoss",),
    "net income loss": ("NetIncomeLoss",),
    "operating income": ("OperatingIncomeLoss",),
    "stockholders equity": ("StockholdersEquity",),
    "public float": ("EntityPublicFloat",),
    "accrued liabilities": ("AccruedLiabilitiesCurrent",),
}
CONCEPT_DICTIONARY_VERSION = "v1.0"


@dataclass(frozen=True)
class RetrievalQuery:
    """A gold-blind query: natural-language question + issuer + cutoff."""

    question: str
    issuer: str
    source_cutoff: date | None = None
    target_fiscal_year: str | None = None


def _concepts_for(question: str) -> set[str]:
    """Public concept-dictionary lookup: question text -> XBRL concept names.

    Uses ONLY the public dictionary (never case payloads). The question is
    lowercased and matched against the dictionary's natural-language keys.
    """
    q = question.lower()
    concepts: set[str] = set()
    for terms, xs in CONCEPT_DICTIONARY.items():
        if terms in q:
            concepts.update(xs)
    # Also match bare tokens against dictionary entries whose key is a single
    # word (e.g. "assets", "revenue") to catch short questions.
    for token in re.findall(r"[a-z0-9]+", q):
        for terms, xs in CONCEPT_DICTIONARY.items():
            if " " not in terms and terms == token:
                concepts.update(xs)
    return concepts


def _filter_issuer(corpus: FullCorpus, issuer: str) -> list:
    """Filter corpus units to one issuer (mirrors base.py _include)."""
    return [u for u in corpus.units if (u.document_id or "").startswith(f"{issuer}-")]


def rrf_retrieve(
    corpus: FullCorpus,
    query: RetrievalQuery,
    top_k: int = 20,
    *,
    k: float = RRF_CONST,
    top_n: int = RRF_TOP_N,
) -> tuple[RankedResult, ...]:
    """R3: Reciprocal Rank Fusion over BM25 + dense (reuses existing retrievers).

    Each retriever ranks the per-issuer corpus; RRF score = sum(1/(k+rank)).
    Dense is optional (skipped when the model cache is absent); if skipped,
    RRF degrades to BM25 ranking (reported honestly in the caller).
    """
    issuer_units = _filter_issuer(corpus, query.issuer)
    if not issuer_units:
        return ()

    # Reuse existing BM25 over the per-issuer slice.
    sub_corpus = FullCorpus(
        tuple(issuer_units), tuple(corpus.documents), corpus.by_document,
    )
    r1 = bm25_retrieve(sub_corpus, query.question, top_k=top_n)

    # Reuse existing dense (skipped gracefully when model cache absent).
    try:
        r2 = dense_retrieve(sub_corpus, query.question, top_k=top_n)
    except Exception:
        r2 = None

    scores: dict[str, float] = {}
    doc_rank: dict[str, int] = {}
    for rank, r in enumerate(r1, start=1):
        scores[r.evidence_id] = scores.get(r.evidence_id, 0.0) + 1.0 / (k + rank)
    if r2 is not None:
        for rank, r in enumerate(r2, start=1):
            scores[r.evidence_id] = scores.get(r.evidence_id, 0.0) + 1.0 / (k + rank)

    ranked = sorted(
        ((scores[uid], uid) for uid in scores),
        key=lambda item: (-item[0], item[1]),
    )[:top_k]
    by_id = {u.evidence_id: u for u in issuer_units}
    return tuple(
        RankedResult(evidence_id=uid, document_id=by_id[uid].document_id,
                     score=score, rank=rank)
        for rank, (score, uid) in enumerate(ranked, start=1)
    )


def concept_retrieve(
    corpus: FullCorpus,
    query: RetrievalQuery,
    top_k: int = 20,
) -> tuple[RankedResult, ...]:
    """R4: concept-graph proxy — concept-dictionary overlap + temporal filter.

    Gold-blind: uses ONLY the public concept dictionary + question text. A unit
    scores higher when its concept is in the dictionary for the question. Units
    whose filing_date is after the source_cutoff are EXCLUDED (temporal proxy).

    Returns an empty tuple when the dictionary yields no concept for the
    question — an honest "no candidate" (the caller routes to ABSTAIN).
    """
    concepts = _concepts_for(query.question)
    if not concepts:
        return ()

    issuer_units = _filter_issuer(corpus, query.issuer)
    scored: list[tuple[float, object]] = []
    for u in issuer_units:
        if query.source_cutoff is not None and u.filing_date > query.source_cutoff:
            continue  # future source — exclude (temporal filter)
        score = 1.0 if (u.concept and u.concept in concepts) else 0.0
        if score > 0:
            scored.append((score, u))
    scored.sort(key=lambda item: (-item[0], getattr(item[1], "evidence_id", "")))
    return tuple(
        RankedResult(evidence_id=u.evidence_id, document_id=u.document_id,
                     score=score, rank=rank)
        for rank, (score, u) in enumerate(scored[:top_k], start=1)
    )


# Re-export existing retrievers so the harness imports one consistent surface.
from finvest.retrieval.full_corpus import bm25_retrieve, dense_retrieve  # noqa: E402
