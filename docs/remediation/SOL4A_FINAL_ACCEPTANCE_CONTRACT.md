# SOL-4A Final Acceptance Contract

**Status:** Frozen for the final independent SOL-4A review. This contract is the
complete Task 5 acceptance scope. A reviewer may report implementation failures
against it but must not add unrelated requirements.

## 1. Authoritative evidence mapping

Production corpus construction has exactly one entry point:
`adapt_evidence_spans(...)`. It maps each validated `EvidenceSpanV1` to one
immutable `CorpusRecord` as follows:

| Corpus field | Authoritative source |
| --- | --- |
| `schema_version` | frozen `retrieval-corpus-record.v3` |
| `source_schema_version` | `EvidenceSpanV1.schema_version` |
| `evidence_id` | `EvidenceSpanV1.content_hash` |
| `document_id` | `EvidenceSpanV1.document_id` |
| `source_id` | optional adapter input when the source system has a distinct ID |
| `issuer_id` | `EvidenceSpanV1.issuer_id` |
| `asset_id` | explicit adapter input, defaulting to `issuer_id` |
| `text` | exact `EvidenceSpanV1.text`, without reconstruction or normalization |
| `valid_from` | deterministic end date of `report_period` |
| `valid_to` | optional explicit adapter input |
| `source_time` | `EvidenceSpanV1.source_date` |
| `page_id` / `block_id` | corresponding `EvidenceSpanV1` fields |
| remaining source provenance | report period, bounding box, section, text/content hashes, extraction confidence, and provider |
| structured numerical values | optional named adapter input encoded under the numeric policy below |

The adapter rejects missing required identities, duplicate evidence IDs,
invalid validity intervals, and structured-value keys that do not identify an
adapted span. It returns a sealed `AuthoritativeCorpus`; callers cannot create
that type through its public constructor. Handcrafted `CorpusRecord` values
remain available only for fixture/exploratory tests and cannot enter final mode.

The evidence graph continues to return document candidates. For adapted
records, the retrieval boundary resolves each graph-reachable document ID to
its indexed span records. This is an adapter connection, not a graph traversal
or temporal-semantics change.

## 2. Canonical corpus fingerprint schema

Schema v3 is compact canonical JSON encoded as UTF-8 with sorted object keys,
deterministic record ordering by `evidence_id`, explicit field names, and no
delimiter concatenation. Every corpus field listed above is serialized,
including `document_id`, page/block identity, validity interval, source time,
exact stored text, source provenance, and sorted named structured values.

SHA-256 is computed over those canonical bytes. Fingerprinting performs no
NFKC/NFC/NFD normalization, case conversion, trimming, whitespace collapse,
stemming, tokenization, or punctuation rewriting. Method-specific processing
belongs to backend dependency provenance and does not alter shared corpus
identity.

## 3. Numeric policy

- Built-in Python `int` is supported as a tagged arbitrary-precision base-10
  string. `bool` is rejected before the integer path.
- Finite `Decimal` is supported as tagged exact plain notation. Fractional
  trailing zeroes are removed, exponents are expanded, nonzero sign is
  preserved, and all signed zero representations canonicalize to `0`.
- Built-in Python `float` is supported as tagged exact `float.hex()` after a
  finite-value check. Positive and negative zero remain distinct.
- Exact source numerical text is a separate tagged string type.
- Missing values have an explicit null tag.
- NumPy integers, NumPy floats, and all unsupported third-party scalar types
  are rejected. No implicit NumPy-to-Python conversion is permitted.
- NaN, signed NaN, and positive/negative Infinity are rejected for every
  supported numerical path.

## 4. Strict fingerprint representation

Every reported fingerprint must satisfy all of the following before equality
comparison: `type(value) is str`, length 64, and lowercase ASCII hexadecimal
matching `[0-9a-f]{64}`. String subclasses, arbitrary equality objects,
uppercase text, whitespace, prefixes, wrong lengths, and non-hex characters
are invalid. Each of the six methods is checked independently against a fresh
recomputation from its actual corpus.

## 5. Trusted backend instances

Final mode accepts only retriever instances registered by the approved
production factory. The factory consumes a sealed `AuthoritativeCorpus`,
constructs the concrete backend, creates a run-scoped instance identity, and
records immutable dependency provenance. `RetrievalMetadata` remains an
artifact-facing description and is never proof of construction or execution.

Each trusted identity binds the canonical method ID, concrete Python backend
type, instance ID, run ID, authoritative corpus receipt, corpus fingerprint,
and complete dependency chain. Direct constructors remain usable for focused
non-final tests but their instances are untrusted by final mode.

## 6. Successful execution evidence

Only a registered backend instance may receive an internal execution receipt.
The receipt is issued after successful retrieval and binds method ID, backend
instance ID, run ID, corpus fingerprint, query digest, `valid_at`, explicit
`source_cutoff`, `top_k`, dependency digest, successful status, and canonical
output digest.

Dense and reranker methods additionally require successful real inference on
the instantiated backend during that retrieval. Constructor success, cached
metadata, partially present files, or a Boolean claim cannot produce a receipt.
The verifier method requires both inherited reranker inference and verifier
execution. Receipts are stored in the internal trusted-instance registry;
caller-created receipt-shaped dataclasses or copied metadata are not accepted.

## 7. Composite dependency provenance

The production factory records and final mode validates these exact component
roles:

- `bm25`: lexical backend package/version and tokenizer contract/version.
- `dense`: dense backend package/version and immutable model ID/revision.
- `static_kg`: graph backend identity and graph schema/version.
- `temporal_kg`: static graph requirements plus temporal eligibility contract/version.
- `temporal_kg_rerank`: temporal graph requirements plus reranker backend
  package/version, model ID, immutable revision, and successful inference.
- `temporal_kg_verify`: the full reranker chain plus verifier implementation
  and version, and verifier model identity/revision when model-backed.

Missing, duplicate, unexpected, copied, or mismatched dependency roles fail.
The verifier currently uses the deterministic `source-time-verifier` v1.0.0;
it does not claim a separate learned verifier model.

## 8. Final six-method boundary

Final comparison requires exactly the six canonical method IDs, no aliases or
duplicates, `top_k=5`, explicit `valid_at` and `source_cutoff`, one shared sealed
authoritative corpus, one factory run ID, strict independently recomputed
fingerprints, trusted instances, complete dependencies, matching execution
receipts, finite scores, unique evidence IDs, and canonical rank/score/evidence
ordering. Fixture or exploratory mode, handcrafted corpora, stale/copied
receipts, mixed corpora/queries/methods, and `production_unavailable` fail.

The graph candidate boundary, valid-time/source-time semantics, citation metric
formulas, and evaluator isolation remain unchanged.

## 9. External blockers

Missing dense executable weights, the absent verified immutable reranker
revision/snapshot, unproven real dense/reranker inference, and the unresolved
exact release dependency lock are external blockers. A blocked backend remains
`production_unavailable`, emits no successful receipt, and prevents a final
Task 5 result. Skipped real-model tests document blockers but are never counted
as production verification. Model downloads are not part of SOL-4A.

## 10. Required adversarial evidence

PASS requires focused tests that directly inspect canonical bytes and prove:

1. all schema-v3 fields, especially document/page/block and separate time
   fields, affect identity and adapter conversion is deterministic;
2. handcrafted/fixture records cannot enter final mode;
3. integer, Decimal, built-in float, source text, null, bool, non-finite, NumPy,
   and unsupported-scalar behavior follows Section 3;
4. every malformed fingerprint case in Section 4 fails independently;
5. fabricated retrievers, metadata, flags, backend IDs, execution Booleans,
   copied identities, and receipt-shaped values fail;
6. receipts from another corpus, query, method, backend instance, or run fail;
7. constructor-only/partial dense and reranker states fail;
8. every composite dependency omission or mismatch fails, while one complete
   factory-issued chain validates;
9. the existing six-method, graph, temporal, citation, finite-score, and
   deterministic-order regression suite remains green.

The next independent review is limited to this contract. SOL-4A implementation
may be internally fixed while real final production execution remains externally
blocked. No implementation session may declare SOL-4A PASS or Task 5 GO.
