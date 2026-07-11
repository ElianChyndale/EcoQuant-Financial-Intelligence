# Task 5 graph-assisted retrieval repair

Implementation completed from checkpoint `837e443` in the isolated worktree at
`D:\Aireland\.worktrees\task1-secure-repositories\ecoquant-financial-intelligence`.

## RED/GREEN record

RED was observed at 2026-07-11 (Asia/Shanghai): the new source-cutoff query
test failed because `RetrieverQuery` did not accept `source_cutoff`; the hostile
edge test failed because no adjacency traversal existed.  GREEN was observed at
2026-07-11 after the implementation: retrieval 32 passed, temporal graph 6
passed, and corpus contract 4 passed.

## Changes

- `TemporalEvidenceGraph.retrieval_candidate_evidence_ids()` resolves the
  issuer seed and walks immutable, non-evaluator-only `retrieval_edges()`;
  it returns document/evidence nodes reached through adjacency, deterministically.
- `temporal_retrieval_candidate_evidence_ids()` applies valid time and source
  availability separately. `valid_at` is the queried financial applicability
  time; `source_cutoff` is the latest publication/observation time permitted.
- The builder creates a source-derived `Issuer -> Document` `CONTAINS` path.
  It uses only the approved relation enum and preserves prior claim semantics.
- `RetrieverQuery` preserves `cutoff` compatibility and exposes `valid_at`,
  `source_cutoff`, and `effective_source_cutoff`. `CorpusRecord.source_time`
  is source metadata, not an evaluator annotation.
- KG retrieval uses the graph APIs above as its candidate boundary. Static KG
  intentionally has no temporal filter. Temporal KG invokes temporal graph
  traversal. Lexical scoring only ranks graph-derived corpus records.
- The verifier returns `invalid_for_requested_time` distinctly from
  `published_after_source_cutoff`.
- `Edge` is frozen and `retrieval_edges()` excludes every `evaluator_only`
  edge, including when the retriever receives the full graph object.

## Tests and integrity checks

Commands passed:

- `python -m pytest -q tests/research/test_retrieval_methods.py` — 32 passed
- `python -m pytest -q tests/unit/test_temporal_graph.py` — 6 passed
- `python -m pytest -q tests/research/test_corpus_contract.py` — 4 passed
- `git diff --check 837e443..HEAD` (re-run after the commit)

The added hostile test proves an answer reached only by an evaluator-only edge
is absent, then becomes retrievable only after a source-derived edge is added.
The existing no-label-access retrieval test remains green. Task 3 artifacts are
unchanged, no Task 6 files exist, fixture metadata remains fixture-mode, and
the central six-method comparison boundary is unchanged.

## Limitations

This fixture graph uses issuer-to-document source links, so concept resolution
is intentionally limited to source-visible issuer seeds. It does not infer
financial relationships beyond the checked document structure.
