"""FinVEST leakage auditor (PREREGISTRATION + A0).

Detects whether any training/calibration/inference feature reads gold-derived
information, and whether splits leak across issuers, document families,
templates, or evidence families.

Gold-derived inputs that must never enter a non-oracle pipeline:
- gold evidence IDs, gold pages, gold relevance,
- gold requirement coverage, gold answers,
- gold calculation programs, gold temporal/decision labels.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

GOLD_TOKENS = (
    "gold_", "gold", "relevant_evidence", "relevant_by_question",
    "gold_source_ids", "gold_page_ids", "gold_block_ids",
    "gold_answer", "gold_program", "gold_relevance", "gold_label",
)


def audit_source_for_gold(source_text: str, *, function_name: str | None = None) -> list[str]:
    """Return gold-shaped identifiers in a source (optionally one function).

    Used by CI to fail whenever a non-oracle module reads gold fields.
    Evaluation-only functions (explicitly named ``*_from_gold`` /
    ``*_evaluate*``) are exempt only when the caller scopes by function name.
    """
    mentions: set[str] = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", source_text):
        lowered = token.lower()
        if any(g in lowered for g in GOLD_TOKENS):
            mentions.add(token)
    return sorted(mentions)


def audit_split(
    *,
    issuer_of: Mapping[str, str],
    family_of: Mapping[str, str],
    train: Sequence[str],
    test: Sequence[str],
    template_of: Mapping[str, str] | None = None,
) -> list[str]:
    """Return split-leakage violations across issuer/family/template levels."""
    violations: list[str] = []
    train_set, test_set = set(train), set(test)
    for level_name, mapping in (
        ("issuer", issuer_of),
        ("document_family", family_of),
        ("question_template", template_of or {}),
    ):
        if not mapping:
            continue
        train_keys = {mapping[c] for c in train_set if c in mapping}
        test_keys = {mapping[c] for c in test_set if c in mapping}
        overlap = train_keys & test_keys
        if overlap:
            violations.append(f"{level_name} spans splits: {sorted(overlap)}")
    return violations


def hash_content(text: str) -> str:
    """Exact-content hash for near-duplicate detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def minhash_sketch(text: str, *, shingle: int = 5, n_hashes: int = 64) -> set[int]:
    """Simple MinHash-style sketch for near-duplicate detection."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    shingles = {
        " ".join(tokens[i:i + shingle])
        for i in range(max(0, len(tokens) - shingle + 1))
    }
    hashes = {int(hashlib.md5(s.encode()).hexdigest()[:8], 16) for s in shingles}
    return set(sorted(hashes)[:n_hashes])


def jaccard(a: set[int], b: set[int]) -> float:
    """Jaccard similarity of two sketches."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def audit_duplicate_pairs(
    text_by_id: Mapping[str, str],
    *,
    threshold: float = 0.6,
) -> list[tuple[str, str, float]]:
    """Return (id_a, id_b, jaccard) for near-duplicate text pairs."""
    sketches = {cid: minhash_sketch(text) for cid, text in text_by_id.items()}
    ids = sorted(sketches)
    pairs: list[tuple[str, str, float]] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = jaccard(sketches[ids[i]], sketches[ids[j]])
            if sim >= threshold:
                pairs.append((ids[i], ids[j], sim))
    return pairs
