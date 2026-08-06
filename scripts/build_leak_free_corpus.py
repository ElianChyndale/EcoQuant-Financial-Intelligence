"""Build and freeze the gold-blind (leak-free) SEC retrieval corpus (Phase 2).

Reads ONLY:
  - SOURCE_MANIFEST.json (eligible sources)
  - SEC companyfacts JSON (research/cache/sec/*_companyfacts.json)

Never reads gold. Produces:
  research/corpus/corpus.jsonl        raw corpus records (gitignored cache)
  research/corpus/CORPUS_MANIFEST.json corpus identity + source hashes
  research/corpus/CORPUS.sha256       fingerprint of corpus.jsonl
  research/corpus/SPLIT_MANIFEST.json issuer-disjoint folds + leak audit
  research/corpus/SOURCE_MANIFEST.json eligible raw sources + sha256

Usage:
    python scripts/build_leak_free_corpus.py [--cache research/cache]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS_DIR = ROOT / "research" / "corpus"


def _git_head(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "research/cache")
    parser.add_argument("--out", type=Path, default=CORPUS_DIR)
    parser.add_argument("--commit", default=None, help="builder commit sha (default: git HEAD)")
    args = parser.parse_args()

    from finvest.benchmark.builders.leak_free_corpus import (
        build_leak_free_corpus,
        build_source_manifest,
        corpus_manifest,
    )

    commit = args.commit or _git_head(ROOT)
    corpus = build_leak_free_corpus(args.cache)
    args.out.mkdir(parents=True, exist_ok=True)

    # corpus.jsonl — raw records (cache-like; gitignored).
    corpus_jsonl = args.out / "corpus.jsonl"
    with corpus_jsonl.open("w", encoding="utf-8") as handle:
        for r in corpus.records:
            handle.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    corpus_sha = hashlib.sha256(corpus_jsonl.read_bytes()).hexdigest()

    # CORPUS.sha256 — fingerprint of corpus.jsonl.
    (args.out / "CORPUS.sha256").write_text(corpus_sha + "\n", encoding="utf-8")

    # CORPUS_MANIFEST.json — identity + source hashes + split manifest.
    manifest = corpus_manifest(corpus, builder_commit=commit)
    manifest["corpus_jsonl_sha256"] = corpus_sha
    (args.out / "CORPUS_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")

    # SPLIT_MANIFEST.json.
    (args.out / "SPLIT_MANIFEST.json").write_text(
        json.dumps(corpus.split_manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    # SOURCE_MANIFEST.json — eligible raw sources.
    source_manifest = build_source_manifest(args.cache)
    (args.out / "SOURCE_MANIFEST.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")

    print(f"corpus_id : {corpus.corpus_id}")
    print(f"records   : {len(corpus.records)}")
    print(f"corpus.jsonl sha256 : {corpus_sha}")
    print(f"builder   : {commit}")
    print(f"gold tokens in corpus: {corpus.split_manifest['audit']['gold_tokens_in_corpus']}")
    print(f"output    : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
