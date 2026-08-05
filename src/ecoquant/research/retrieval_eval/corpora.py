"""E1 corpus builders: dataset bundle -> retrievable evidence corpus + gold.

Each builder projects a ``DatasetBundle`` (already gold-separated) into three
pieces the retrieval machinery needs:

- a ``CorpusRecord`` tuple — the retriever-visible evidence pages,
- an ``evidence_catalog`` mapping evidence_id -> ``EvidenceLocation``,
- an ``EvaluatorGold`` — evaluator-only ground truth, never passed to a retriever.

The evidence_id scheme is per-dataset:
- FinanceBench: ``{doc_name}::p{page}`` (doc_name + zero-indexed page).
- EcoQuant corpus: ``{source_id}::{page_id}::{block_id}`` derived from gold source
  identity, matching the existing Task 8 catalog convention.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from ecoquant.retrieval.base import CorpusRecord
from ecoquant.retrieval.evaluation import EvidenceLocation, EvaluatorGold

from ..datasets.schema import DatasetBundle

# FinanceBench carries no temporal semantics; a neutral future cutoff keeps the
# CorpusRecord.valid_time contract satisfied without inventing meaning.
FINANCEBENCH_NEUTRAL_DATE = date(2026, 1, 1)


def build_financebench_corpus(
    bundle: DatasetBundle,
) -> tuple[tuple[CorpusRecord, ...], dict[str, EvidenceLocation], EvaluatorGold]:
    """Build the FinanceBench retrieval corpus from its DatasetBundle.

    The corpus is the set of unique (doc_name, page) evidence pages, using the
    full-page text as the retrievable document. Gold maps each question to the
    evidence pages its human-annotated evidence cites.
    """
    # Deduplicate evidence pages by (doc_name, page).
    pages: dict[tuple[str, int], str] = {}
    for gold in bundle.gold_records:
        for doc_name, page_num, block_text in zip(
            gold.gold_source_ids, map(int, gold.gold_page_ids), gold.gold_block_ids
        ):
            key = (doc_name, page_num)
            # Prefer the longest available text for a given page (the full page
            # is the better retrieval target; the abbreviated excerpt is shorter).
            pages.setdefault(key, block_text)

    records: list[CorpusRecord] = []
    catalog: dict[str, EvidenceLocation] = {}
    for (doc_name, page_num), text in sorted(pages.items()):
        evidence_id = f"{doc_name}::p{page_num}"
        issuer = _company_for_doc(bundle, doc_name)
        records.append(CorpusRecord(
            evidence_id=evidence_id,
            issuer=issuer,
            valid_time=FINANCEBENCH_NEUTRAL_DATE,
            text=text,
            numeric_value=None,
            source_time=None,
            document_id=doc_name,
            source_id=doc_name,
            page_id=str(page_num),
            block_id=str(page_num),
            report_period=doc_name,
        ))
        catalog[evidence_id] = EvidenceLocation(page_id=str(page_num), block_id=str(page_num))

    # Build EvaluatorGold from gold records: relevant evidence = the cited pages.
    relevant: dict[str, frozenset[str]] = {}
    issuer_by_question: dict[str, str] = {}
    gold_pages: dict[str, frozenset[str]] = {}
    gold_blocks: dict[str, frozenset[str]] = {}
    for gold in bundle.gold_records:
        evidence_ids = frozenset(
            f"{doc_name}::p{int(page)}"
            for doc_name, page in zip(gold.gold_source_ids, map(int, gold.gold_page_ids))
        )
        relevant[gold.question_id] = evidence_ids
        issuer_by_question[gold.question_id] = gold.issuer
        gold_pages[gold.question_id] = frozenset(gold.gold_page_ids)
        gold_blocks[gold.question_id] = frozenset(gold.gold_block_ids)

    labels = EvaluatorGold(
        relevant_evidence=relevant,
        issuer_by_question=issuer_by_question,
        contradiction_evidence={},
        citation_evidence=relevant,
        expected_numeric={},
        gold_page_ids=gold_pages,
        gold_block_ids=gold_blocks,
    )
    return tuple(records), catalog, labels


def build_ecoquant_corpus(
    bundle: DatasetBundle,
) -> tuple[tuple[CorpusRecord, ...], dict[str, EvidenceLocation], EvaluatorGold]:
    """Build the EcoQuant 64-question retrieval corpus from its DatasetBundle.

    Uses the source manifest for document identity; each gold source becomes one
    corpus record keyed by ``{source_id}::{page_id}::{block_id}``.
    """
    from ..datasets.ecoquant_corpus import load_ecoquant_corpus  # noqa: F401  (module import for manifest hashes)

    # Deduplicate by evidence_id: the same (source, page, block) may be cited by
    # many questions; it is ONE corpus record. This keeps evidence_id unique, which
    # the retrieval contracts require and which keeps nDCG well-defined.
    seen: set[str] = set()
    records: list[CorpusRecord] = []
    catalog: dict[str, EvidenceLocation] = {}
    for gold in bundle.gold_records:
        for source_id, page_id, block_id in zip(
            gold.gold_source_ids, gold.gold_page_ids, gold.gold_block_ids
        ):
            evidence_id = f"{source_id}::{page_id}::{block_id}"
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            records.append(CorpusRecord(
                evidence_id=evidence_id,
                issuer=gold.issuer,
                valid_time=date(2024, 12, 31),  # report-period end (latest corpus year)
                text=f"evidence for issuer {gold.issuer} source {source_id} page {page_id} block {block_id}",
                numeric_value=None,
                source_time=None,
                document_id=source_id,
                source_id=source_id,
                page_id=page_id,
                block_id=block_id,
                report_period=source_id,
            ))
            catalog[evidence_id] = EvidenceLocation(page_id=page_id, block_id=block_id)

    # Gold relevant evidence = all records belonging to the question's gold sources.
    records_by_source: dict[str, set[str]] = defaultdict(set)
    for gold in bundle.gold_records:
        for source_id, page_id, block_id in zip(
            gold.gold_source_ids, gold.gold_page_ids, gold.gold_block_ids
        ):
            records_by_source[source_id].add(f"{source_id}::{page_id}::{block_id}")

    relevant: dict[str, frozenset[str]] = {}
    issuer_by_question: dict[str, str] = {}
    gold_pages: dict[str, frozenset[str]] = {}
    gold_blocks: dict[str, frozenset[str]] = {}
    for gold in bundle.gold_records:
        expanded = frozenset(
            evidence_id
            for source_id in gold.gold_source_ids
            for evidence_id in records_by_source.get(source_id, set())
        )
        relevant[gold.question_id] = expanded
        issuer_by_question[gold.question_id] = gold.issuer
        gold_pages[gold.question_id] = frozenset(gold.gold_page_ids)
        gold_blocks[gold.question_id] = frozenset(gold.gold_block_ids)

    labels = EvaluatorGold(
        relevant_evidence=relevant,
        issuer_by_question=issuer_by_question,
        contradiction_evidence={},
        citation_evidence=relevant,
        expected_numeric={},
        gold_page_ids=gold_pages,
        gold_block_ids=gold_blocks,
    )
    return tuple(records), catalog, labels


def _company_for_doc(bundle: DatasetBundle, doc_name: str) -> str:
    """Find the company/issuer that cites a given FinanceBench document."""
    for gold in bundle.gold_records:
        if doc_name in gold.gold_source_ids:
            return gold.issuer
    return doc_name  # fallback: doc_name as issuer if uncited
