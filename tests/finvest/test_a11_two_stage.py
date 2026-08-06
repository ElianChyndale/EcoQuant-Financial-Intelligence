"""Tests for the A11 two-stage experiment harness (Phase 3).

Uses a fixture cache + freeze_day1-generated fixture cases so gold evidence
IS present in the fixture corpus (real recall path). Asserts:
- three separated layers exist (retrieval / set_selection / verification);
- R1 ranks candidates; S4 is flagged upper_bound_only / not_headline_eligible;
- V-layer returns the three verification states;
- the retrieval pool does NOT contain gold structure (leakage audit clean);
- ABSTAIN / REVIEW / ANSWER buckets are populated honestly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1
from finvest.human_study.protocol_config import V0_2_DRAFT


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Fixture cache + freeze_day1 day1 dir (self-contained, CI-safe).

    Also writes a minimal SOLO_ANNOTATIONS.jsonl derived from the fixture
    cases' own gold (so the harness has an evaluation set whose gold evidence
    IS in the fixture corpus). This is a TEST fixture, not human annotation —
    the honest markers make that explicit.
    """
    tmp = tmp_path_factory.mktemp("a11")
    cache = tmp / "cache"
    sec = cache / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
        encoding="utf-8"
    )
    for ticker in ("aapl", "msft", "ko", "eqix", "jnj", "ups"):
        (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")
    day1 = tmp / "day1"
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1, min_cases=1, cache_dir=cache,
                protocol=V0_2_DRAFT)

    # Minimal synthetic SOLO_ANNOTATIONS from the fixture cases (test-only).
    manifest = json.loads((day1 / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    cases = manifest["sealed"]["base_candidates_queue"]
    lines = []
    for c in cases:
        rec = {
            "case_id": c["case_id"],
            "evidence_package_hash": "test-fixture",
            "evidence_package_version": "1.0",
            "annotation_protocol_version": "solo-v1",
            "annotation_round": 1,
            "reviewer_id": "A11_TEST",
            "status": "SOLO_PROVISIONAL",
            "route": "ANSWER" if c.get("gold_answer") else "ABSTAIN",
            "human_answer": str(c.get("gold_answer", {}).get("value", "")),
            "selected_evidence_ids": [it["evidence_id"] for it in c.get("evidence_items", [])],
            "human_inputs": {},
            "confidence": "MEDIUM",
            "derived": {},
        }
        lines.append(json.dumps(rec))
    (day1 / "SOLO_ANNOTATIONS.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return day1, cache


def test_a11_runs_with_layers(env) -> None:
    """The two-stage harness runs end-to-end with three separated layers."""
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)

    assert result["experiment"] == "A11_TWO_STAGE"
    assert "retrieval" in result["per_case"][0]
    assert "set_selection" in result["per_case"][0]
    assert "verification" in result["per_case"][0]
    assert "R1_bm25" in result["per_case"][0]["retrieval"]
    assert "R3_rrf" in result["per_case"][0]["retrieval"]
    assert "R4_concept_temporal" in result["per_case"][0]["retrieval"]


def test_a11_retrieval_ranks_candidates(env) -> None:
    """R1 returns ranked candidates with recall metrics."""
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)
    r1 = result["per_case"][0]["retrieval"]["R1_bm25"]
    assert r1["candidate_pool_size"] >= 1
    assert 0.0 <= r1["recall_at_1"] <= 1.0
    assert "mrr" in r1
    assert "stale_rate" in r1


def test_a11_s4_oracle_flagged(env) -> None:
    """S4 oracle is explicitly flagged as upper-bound-only."""
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)
    ss = result["per_case"][0]["set_selection"]
    oracle_keys = [k for k in ss if "S4_oracle" in k]
    assert oracle_keys, "expected an S4_oracle set-selection key"
    first = ss[oracle_keys[0]]
    assert first.get("is_oracle") is True
    assert first.get("upper_bound_only") is True
    assert first.get("not_headline_eligible") is True


def test_a11_verification_three_states(env) -> None:
    """V-layer returns temporal/numerical/joint verdicts."""
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)
    for c in result["per_case"]:
        v = c["verification"]
        assert "joint_valid" in v
        assert "temporal" in v
        assert "numerical" in v
        assert v["temporal"]["valid"] in (True, False)


def test_a11_leakage_audit_clean(env) -> None:
    """The corpus leakage audit reports zero gold tokens / violations."""
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)
    audit = result["corpus"]["leakage_audit"]
    assert audit["gold_tokens_in_corpus"] == []
    assert audit["cross_split_leakage_violations"] == []


def test_a11_buckets_honest(env) -> None:
    """Decisions are reported in ANSWER/REVIEW/ABSTAIN buckets (no gold folding)."""
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)
    decisions = result["decisions"]
    assert set(decisions) == {"ANSWER", "REVIEW", "ABSTAIN"}
    total = sum(decisions.values())
    assert total == result["n_cases"]
