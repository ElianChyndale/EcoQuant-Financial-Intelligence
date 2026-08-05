# FinanceBench Public Sample — Dataset Card

## Identity

- **Dataset ID:** `financebench-sample-v1`
- **Adapter version:** `0.1.0`
- **Source:** https://github.com/patronus-ai/financebench
- **Retrieval date:** 2026-08-05

## Content

- **Scale:** 150 questions over real 10-K/10-Q/8-K/earnings reports of **32 public companies** (84 documents).
- **Question types:** `metrics-generated` (50), `domain-relevant` (50), `novel-generated` (50).
- **Fields per question:** `financebench_id`, `company`, `doc_name`, `question_type`,
  `question_reasoning`, `question`, `answer` (human gold), `justification`,
  `dataset_subset_label`, `evidence` (list of objects).

## Evidence semantics

Each `evidence` object carries:

- `evidence_text` — abbreviated excerpt
- `evidence_text_full_page` — full page text
- `doc_name` — joining key to `financebench_document_information.jsonl`
- `evidence_page_num` — **zero-indexed integer** (FinanceBench convention)

> **Page convention:** FinanceBench page numbers are zero-indexed integers. The
> EcoQuant corpus uses the `p63` form. Convert before any cross-dataset comparison.

## Gold semantics

- `answer` is the human-annotated gold answer.
- `evidence` (doc_name + page_num + text) is the page-level gold evidence.
- The adapter projects `doc_name(s)` → `gold_source_ids`, page numbers → `gold_page_ids`,
  and evidence text prefix → `gold_block_ids` (FinanceBench has no block IDs; the text
  prefix is a deterministic surrogate).

## License and redistribution

- **License:** **unconfirmed** — the upstream repository does not declare an explicit
  license (no LICENSE file or terms found).
- **Redistribution status:** `cache_only`.
- Raw JSONL lives in `research/cache/financebench/` (gitignored). Only source hashes and
  derived metadata are committed. Raw PDFs are not part of this adapter.
- **Do not** redistribute the JSONL or claim permission to redistribute without
  confirming upstream terms.

## Split and leakage

- **Split unit:** company (32 companies). A question's gold evidence stays entirely
  within its company's split.
- Multi-document questions (evidence spanning several doc_names) are atomic: all
  documents referenced by one question belong to the same company and therefore the
  same split.
- Gold never enters `PublicQueryCase`; it lives only in `GoldEvaluationRecord`.

## Provenance

- Questions file: `financebench_open_source.jsonl` (SHA-256 recorded in bundle manifest).
- Docs file: `financebench_document_information.jsonl` (SHA-256 recorded in bundle manifest).
- Label provenance: `human_annotated` (upstream human-verified answers).
