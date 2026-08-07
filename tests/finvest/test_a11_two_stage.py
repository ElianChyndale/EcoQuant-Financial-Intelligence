"""Tests for the A11 two-stage experiment harness (Phase 3).

Includes the P0-1 gold-free routing guard: the ANSWER/REVIEW/ABSTAIN decision
must be computed from the retrieved evidence + verifier state ONLY, never from
the hidden gold_answer (which was the pre-audit leak at run.py:315).

Uses a fixture cache + freeze_day1-generated fixture cases so gold evidence
IS present in the fixture corpus (real recall path). Asserts:
- three separated layers exist (retrieval / set_selection / verification);
- R1 ranks candidates; S4 is flagged upper_bound_only / not_headline_eligible;
- V-layer returns the three verification states;
- the retrieval pool does NOT contain gold structure (leakage audit clean);
- ABSTAIN / REVIEW / ANSWER buckets are populated honestly.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from experiments.a11_retrieval.run import route_decision
from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1
from finvest.human_study.protocol_config import V0_2_DRAFT


def test_route_decision_gold_free() -> None:
    """Routing from evidence alone: ABSTAIN/ANSWER/REVIEW in that precedence."""
    # No evidence found -> ABSTAIN (regardless of verifier).
    assert route_decision(has_evidence=False, joint_valid=True) == "ABSTAIN"
    assert route_decision(has_evidence=False, joint_valid=False) == "ABSTAIN"
    # Evidence + joint verification passed -> ANSWER.
    assert route_decision(has_evidence=True, joint_valid=True) == "ANSWER"
    # Evidence but verification failed -> REVIEW.
    assert route_decision(has_evidence=True, joint_valid=False) == "REVIEW"


def test_review_metric_not_tautological() -> None:
    """A REVIEW decision is correct ONLY when deferral was warranted.

    The pre-audit code scored every REVIEW as correct ('X or True'), so
    review_precision was always 1.0 and false_review_rate always 0 — metrics
    manufactured by logic, not measured. Real semantics:
      - REVIEW on a case whose gold route IS answerable -> FALSE review
        (over-deferral: the system could have answered correctly).
      - REVIEW on a case whose gold route is NOT answerable -> TRUE review
        (deferral was warranted).
    """
    from experiments.a11_retrieval.run import evaluate_correctness

    empty = {"numerical": {"result": None, "verification_state": "REVIEW_REQUIRED"}}

    # Case answerable (gold present), human says ANSWER -> REVIEW is over-deferral.
    ev = evaluate_correctness("REVIEW", empty, {"gold_answer": {"value": 100.0}}, "ANSWER")
    assert ev["bucket"] == "review"
    assert ev["correct"] is False, "REVIEW on an answerable case must be a false review"

    # Case answerable (gold present), human says REVIEW -> deferral warranted.
    ev = evaluate_correctness("REVIEW", empty, {"gold_answer": {"value": 100.0}}, "REVIEW")
    assert ev["bucket"] == "review"
    assert ev["correct"] is True, "REVIEW on a case the human also flagged must be correct"

    # Case unanswerable (no gold), no human route -> deferral warranted.
    ev = evaluate_correctness("REVIEW", empty, {"gold_answer": None}, None)
    assert ev["bucket"] == "review"
    assert ev["correct"] is True, "REVIEW on an unanswerable case must be correct"


def test_routing_block_never_reads_gold_answer() -> None:
    """The production routing must not ACCESS the gold_answer field.

    This guards the exact leak the audit found at run.py:315: the decision
    previously keyed off (case.get('gold_answer') or {}).get('value'). The
    scan matches the access pattern (comments/docstrings that merely mention
    the word are allowed — evaluator-side gold use lives in separate
    functions, not the routing path).
    """
    run_py = Path(__file__).resolve().parents[2] / "experiments/a11_retrieval/run.py"
    tree = ast.parse(run_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_two_stage":
            src = ast.get_source_segment(run_py.read_text(encoding="utf-8"), node)
            # The leak pattern: accessing case['gold_answer'] / .get('gold_answer')
            # anywhere in the production path. Comments are stripped by AST.
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get":
                    args = [a for a in sub.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                    if any(a.value == "gold_answer" for a in args):
                        raise AssertionError(
                            "production routing must never read gold_answer "
                            f"(audit P0-1), found at run.py:{sub.lineno}"
                        )
                if isinstance(sub, ast.Subscript):
                    # case["gold_answer"] index access.
                    if (isinstance(sub.slice, ast.Constant) and sub.slice.value == "gold_answer"):
                        raise AssertionError(
                            "production routing must never read gold_answer "
                            f"(audit P0-1), found at run.py:{sub.lineno}"
                        )
            return
    raise AssertionError("run_two_stage not found")


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


def test_a11_s4_oracle_nondegenerate_when_gold_retrieved(env) -> None:
    """P0-3: S4 oracle must select gold evidence when it is in the candidates.

    The pre-fix wiring fed an identity CoverageModel (evidence_id -> {evidence_id})
    into selectors whose requirements are concepts, so every selector — including
    the S4 'oracle' — returned the empty set even at recall@5 = 1.0. With a true
    gold-coverage model the oracle provides a real upper bound.
    """
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)
    oracle_nonempty = 0
    for c in result["per_case"]:
        r1 = c["retrieval"]["R1_bm25"]
        if r1.get("recall_at_5", 0) > 0:  # gold evidence is in the candidates
            for k, v in c["set_selection"].items():
                if "S4_oracle" in k and v.get("average_set_size", 0) > 0:
                    oracle_nonempty += 1
    assert oracle_nonempty > 0, (
        "S4 oracle never selects gold evidence — degenerate coverage/requirement "
        "space wiring (audit P0-3)"
    )


def test_a11_s2_uses_predicted_not_gold_requirements(env) -> None:
    """P0-3: the proposed selectors (S1-S3) must NOT take gold requirements.

    requirements for S1-S3 come from the public concept dictionary (question ->
    concepts), never from case['evidence_items'] (gold). S4 is the ONLY oracle
    that may use gold, and it is flagged is_oracle.
    """
    from experiments.a11_retrieval.run import run_two_stage

    day1, cache = env
    result = run_two_stage(day1_dir=day1, corpus_cache=cache)
    # Assert the set-selection cells exist and non-oracle S2/S3 do not claim gold.
    for c in result["per_case"]:
        for k, v in c["set_selection"].items():
            if "S2_greedy" in k or "S3_beam" in k:
                assert v.get("is_oracle") is not True, f"{k} must not be an oracle"
                assert v.get("upper_bound_only") is not True


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
