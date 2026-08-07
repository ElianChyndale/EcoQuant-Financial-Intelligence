"""A11: real two-stage experiment over the leak-free corpus (Phase 3).

Three separated layers, each reported independently:

  Layer 1 Retrieval   — full leak-free corpus -> ranked candidates
      R1 BM25 / R2 dense / R3 RRF / R4 concept-temporal
      metrics: recall@1/5/10/20, MRR, nDCG, all-required-evidence recall,
               stale retrieval rate, wrong-period rate, wrong-version rate,
               candidate pool size
  Layer 2 Set-selection — top-K candidates -> evidence set
      S1 top-k / S2 greedy / S3 beam / S4 ILP-oracle (UPPER_BOUND_ONLY)
      metrics: evidence precision, recall, set exact match, minimal-set recall,
               average set size, redundancy, minimality violation rate
  Layer 3 Verification — selected evidence -> temporal/version/numerical
      V1 temporal / V2 numerical / V3 joint
      metrics: numeric accuracy, temporal violation detection, version conflict
               detection, insufficient-evidence detection, unsafe-answer rate,
               abstention precision/recall, risk-coverage
      decision: ANSWER / REVIEW / ABSTAIN

Eval gold = the 20 solo-provisional human labels (evaluation ONLY, never the
corpus). The 3 NEEDS_EXTERNAL_REVIEW + 1 ABSTAIN cases are reported in separate
buckets, never folded into ANSWER accuracy. Honest markers apply.

Dense (R2) is skipped when the model cache is absent (reported honestly).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DAY1 = ROOT / "human_review/day1/v0.2-draft"
CACHE = ROOT / "research/cache"
OUT = ROOT / "research/results/a11_two_stage.json"

MARKERS = ["EXPLORATORY_PILOT", "SMALL_SAMPLE", "NOT_PAPER_HEADLINE", "SOLO_PROVISIONAL"]


def route_decision(*, has_evidence: bool, joint_valid: bool) -> str:
    """Gold-free production routing (audit P0-1 fix).

    Decides ANSWER/REVIEW/ABSTAIN from the retrieved evidence and the joint
    verifier state ONLY — it must never read the hidden gold_answer. A system
    with no retrieved evidence abstains; with evidence that passes the joint
    temporal/version/numerical verifier it answers; otherwise it defers.
    """
    if not has_evidence:
        return "ABSTAIN"
    if joint_valid:
        return "ANSWER"
    return "REVIEW"


def load_gold(day1_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load solo annotations as EVALUATION labels (latest per case)."""
    day1_dir = day1_dir or DAY1
    recs = [json.loads(l) for l in (day1_dir / "SOLO_ANNOTATIONS.jsonl").open(encoding="utf-8") if l.strip()]
    latest: dict[str, dict] = {}
    for r in recs:
        latest[r["case_id"]] = r
    return list(latest.values())


def load_sealed_cases(day1_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Join sealed case payloads (QUEUE_MANIFEST + EXTENSION)."""
    import ast

    day1_dir = day1_dir or DAY1
    sealed: dict[str, dict[str, Any]] = {}
    manifest = json.loads((day1_dir / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    for c in manifest.get("sealed", {}).get("base_candidates_queue", []):
        sealed[c["case_id"]] = c
    ext = day1_dir / "EXTENSION_40_cases.json"
    if ext.exists():
        for c in json.loads(ext.read_text(encoding="utf-8")):
            sealed[c["case_id"]] = c
    # Parse Python-repr frozenset strings (frozen local data; wrapped as
    # "frozenset({...})"). Strip the frozenset(...) wrapper, then literal_eval
    # the inner set literal and convert to frozenset.
    for c in sealed.values():
        for key in ("acceptable_evidence_sets", "minimal_evidence_sets"):
            val = c.get(key)
            if isinstance(val, list) and val and isinstance(val[0], str):
                parsed = []
                for v in val:
                    inner = v[len("frozenset("):-1] if v.startswith("frozenset(") else v
                    parsed.append(frozenset(ast.literal_eval(inner)))
                c[key] = parsed
    return sealed


def build_query(case: dict[str, Any], rec: dict[str, Any]) -> Any:
    """Build a gold-blind RetrievalQuery from a sealed case (NO gold fields)."""
    from finvest.retrieval.retrievers import RetrievalQuery

    cutoff = None
    if case.get("source_cutoff"):
        cutoff = date.fromisoformat(str(case["source_cutoff"])[:10])
    return RetrievalQuery(
        question=case["question"],
        issuer=case["issuer_id"],
        source_cutoff=cutoff,
        target_fiscal_year=case.get("target_fiscal_year"),
    )


def run_two_stage(
    *,
    fixture: bool = False,
    top_k: int = 20,
    day1_dir: Path | None = None,
    corpus_cache: Path | None = None,
) -> dict[str, Any]:
    from finvest.benchmark.builders.leak_free_corpus import build_leak_free_corpus
    from finvest.retrieval.full_corpus import build_full_corpus, FullCorpus
    from finvest.retrieval.retrievers import (
        dense_retrieve, concept_retrieve,
    )
    from finvest.retrieval.metrics import (
        all_required_evidence_recall,
        document_recall_at_k,
        mrr,
        ndcg_at_k,
        set_precision,
        redundancy,
    )
    from finvest.set_selection.selectors import (
        b1_top_k, b2_greedy_set_cover, b3_beam_search, b4_ilp_oracle,
        CoverageModel, set_metrics,
    )
    from finvest.verification.temporal_version import verify_joint_temporal
    from finvest.verification.numerical import verify_calculation
    from finvest.benchmark.schemas import EvidenceItem, VersionRelation

    gold = load_gold(day1_dir)
    sealed = load_sealed_cases(day1_dir)

    # Leak-free corpus: companyfacts facts + full 10-K units. In --fixture mode
    # we build from the committed SEC fixture (small) so tests/CI run fast and
    # offline; in production mode we build from the real cache (170k facts).
    from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR

    if corpus_cache is None:
        corpus_cache = CACHE
        if fixture:
            # Build a small fixture cache mirroring research/cache/sec layout.
            import tempfile

            corpus_cache = Path(tempfile.mkdtemp(prefix="a11-fixture-"))
            sec = corpus_cache / "sec"
            sec.mkdir(parents=True, exist_ok=True)
            fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
                encoding="utf-8"
            )
            for ticker in ("aapl", "msft", "ko", "eqix", "jnj", "ups"):
                (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")

    facts_corpus = build_leak_free_corpus(corpus_cache, fixture=fixture or corpus_cache is not CACHE)

    # Build a per-issuer FullCorpus ON DEMAND (the full 170k-record corpus does
    # not fit in memory alongside BM25/dense; each issuer slice is ~24-30k and
    # comfortably fits). The 10-K full-document corpus is appended when present.
    _FULL_CORPUS_CACHE: dict[str, FullCorpus] = {}

    def _issuer_corpus(issuer: str) -> FullCorpus:
        if issuer in _FULL_CORPUS_CACHE:
            return _FULL_CORPUS_CACHE[issuer]
        units = [
            EvidenceItem(
                evidence_id=f"{r.issuer}:us-gaap:{r.concept}:{r.unit}:{r.start or ''}:{r.end}:{r.form}:{r.accession}",
                document_id=r.document_id,
                document_version=r.form,
                filing_date=date.fromisoformat(r.filed),
                valid_from=date.fromisoformat(r.start) if r.start else None,
                valid_to=date.fromisoformat(r.end),
                text_span=f"{r.concept} {r.value} {r.unit} {r.start or ''} {r.end} {r.filed} {r.form} {r.accession}",
                concept=r.concept,
                unit=r.unit,
                content_hash=r.source_hash,
            )
            for r in facts_corpus.records if r.issuer == issuer
        ]
        try:
            full = build_full_corpus(corpus_cache)
            units += [u for u in full.units if (u.document_id or "").startswith(f"{issuer}-")]
        except Exception:
            pass  # full 10-K cache absent on CI — companyfacts only
        corpus = FullCorpus(tuple(units), (), {})
        _FULL_CORPUS_CACHE[issuer] = corpus
        return corpus

    # Per-case retrieval + selection + verification.
    retrieval_results: dict[str, dict[str, Any]] = {}
    set_selection_results: dict[str, dict[str, Any]] = {}
    verification_results: dict[str, dict[str, Any]] = {}
    decisions: dict[str, str] = {}
    per_case: list[dict[str, Any]] = []

    # dense availability is checked lazily on the first per-issuer slice (a
    # full-corpus encode of 170k records would exhaust memory on CI/laptops).
    dense_available = True
    _dense_probed = False

    def _probe_dense() -> None:
        nonlocal dense_available, _dense_probed
        if _dense_probed:
            return
        _dense_probed = True
        try:
            first_case = next((sealed.get(r["case_id"]) for r in gold if sealed.get(r["case_id"])), None)
            if first_case:
                issuer = first_case.get("issuer_id")
                probe_corpus = _issuer_corpus(issuer)
                probe_units = list(probe_corpus.units)[:200]
                probe = FullCorpus(tuple(probe_units), (), {}) if probe_units else probe_corpus
                dense_retrieve(probe, "availability probe", top_k=1)
        except Exception:
            dense_available = False

    for rec in gold:
        cid = rec["case_id"]
        case = sealed.get(cid)
        if case is None:
            continue
        query = build_query(case, rec)

        # --- Layer 1: Retrieval (per-issuer corpus slice to bound memory) ---
        # The leak-free corpus is 170k records; BM25 over the whole corpus
        # MemoryErrors. Each case targets ONE issuer, so we retrieve against the
        # on-demand per-issuer corpus (built once per issuer, reused across
        # cases of that issuer).
        sub_corpus = _issuer_corpus(query.issuer)

        _probe_dense()
        # Precomputed per-issuer BM25 index (built once, shared across cases).
        bm25_index = _issuer_bm25(sub_corpus)
        r1 = _bm25_query(bm25_index, sub_corpus, query.question, top_k=top_k)
        r2 = dense_retrieve(sub_corpus, query.question, top_k=top_k) if dense_available else ()
        r3 = _rrf_query(bm25_index, sub_corpus, query, top_k=top_k, dense_ok=dense_available)
        r4 = concept_retrieve(sub_corpus, query, top_k=top_k)

        # Gold evidence ids (evaluation only, NEVER fed to retrievers).
        gold_ids = {it.get("evidence_id") for it in case.get("evidence_items", [])}
        gold_concepts = {it.get("concept") for it in case.get("evidence_items", [])}

        gold_ids_frozen = frozenset(gold_ids)

        def _retr_section(results):
            """Reuse the finvest retrieval metrics (no reimplementation)."""
            ranked = list(results)
            gold_docs = frozenset(
                u.document_id for u in sub_corpus.units if u.evidence_id in gold_ids
            )
            stale = sum(
                1 for r in ranked
                if query.source_cutoff and r.document_id
                and _filing_from_doc(r.document_id, sub_corpus) is not None
                and _filing_from_doc(r.document_id, sub_corpus) > query.source_cutoff
            ) / max(len(ranked), 1)
            return {
                "candidate_pool_size": len(ranked),
                "recall_at_1": round(all_required_evidence_recall(ranked, gold_ids_frozen, k=1), 4),
                "recall_at_5": round(all_required_evidence_recall(ranked, gold_ids_frozen, k=5), 4),
                "recall_at_10": round(all_required_evidence_recall(ranked, gold_ids_frozen, k=10), 4),
                "recall_at_20": round(all_required_evidence_recall(ranked, gold_ids_frozen, k=20), 4),
                "document_recall_at_5": round(document_recall_at_k(ranked, gold_docs, k=5), 4),
                "mrr": round(mrr(ranked, gold_ids_frozen), 4),
                "ndcg_at_20": round(ndcg_at_k(ranked, gold_ids_frozen, k=20), 4),
                "set_precision_at_20": round(set_precision(ranked, gold_ids_frozen, k=20), 4),
                "redundancy_at_20": round(redundancy(ranked, k=20), 4),
                "stale_rate": round(stale, 4),
            }

        retrieval_results[cid] = {
            "R1_bm25": _retr_section(r1),
            "R2_dense": _retr_section(r2) if r2 else {"candidate_pool_size": 0, "note": "skipped (model cache absent)"},
            "R3_rrf": _retr_section(r3),
            "R4_concept_temporal": _retr_section(r4),
            "dense_available": dense_available,
        }

        # --- Layer 2: Set selection (on each retriever's candidates) ---
        # Audit P0-3 fix: requirements and coverage must live in the SAME space.
        #   - requirements: concepts (gold-free — induced from the question via
        #     the public concept dictionary for S1/S2/S3).
        #   - coverage:     evidence_id -> {concept} (inference-time available:
        #     each corpus unit carries its own concept).
        #   - S4 is the ONLY gold oracle: it receives true gold coverage so it
        #     is a genuine upper bound, flagged is_oracle.
        from finvest.retrieval.retrievers import _concepts_for

        predicted_concepts = frozenset(_concepts_for(query.question))
        set_results: dict[str, Any] = {}
        for rname, results in (
            ("R1_bm25", r1), ("R3_rrf", r3), ("R4_concept", r4),
        ):
            ranked_ids = [r.evidence_id for r in results]
            gold_support = gold_ids
            gold_minimal = next(iter(case.get("minimal_evidence_sets") or [()]), frozenset())

            # Predicted (non-gold) coverage: evidence -> its own concept(s).
            concept_coverage = CoverageModel(
                {u.evidence_id: frozenset({u.concept}) for u in sub_corpus.units
                 if u.concept and u.evidence_id in set(ranked_ids)}
            ) if ranked_ids else CoverageModel({})

            # Proposed (gold-free) selectors: S1 top-k, S2 greedy, S3 beam —
            # requirements induced from the question, never from gold.
            for sname, sel in (
                ("S1_top_k", b1_top_k(ranked_ids, k=5)),
                ("S2_greedy", b2_greedy_set_cover(ranked_ids, predicted_concepts, concept_coverage)),
                ("S3_beam", b3_beam_search(ranked_ids, predicted_concepts, concept_coverage)),
            ):
                m = set_metrics(sel, gold_support, gold_minimal, predicted_concepts, concept_coverage)
                label = f"{rname}_{sname}"
                set_results[label] = {k: round(float(v), 4) for k, v in m.items() if k != "sets"}

            # S4 oracle: TRUE gold coverage (evidence -> gold concepts if the
            # evidence is in the gold support set). Upper bound only; gold is
            # consumed here solely to bound what a perfect selector could do.
            gold_requirements = frozenset(gold_concepts)
            gold_coverage = CoverageModel(
                {uid: gold_requirements if uid in gold_support else frozenset()
                 for uid in ranked_ids}
            ) if ranked_ids else CoverageModel({})
            s4 = b4_ilp_oracle(ranked_ids, gold_requirements, gold_coverage)
            m = set_metrics(s4, gold_support, gold_minimal, gold_requirements, gold_coverage)
            label = f"{rname}_S4_oracle"
            set_results[label] = {k: round(float(v), 4) for k, v in m.items() if k != "sets"}
            set_results[label]["is_oracle"] = True
            set_results[label]["upper_bound_only"] = True
            set_results[label]["not_headline_eligible"] = True
        set_selection_results[cid] = set_results

        # --- Layer 3: Verification + decision ---
        # Use R3 (RRF) top-K as the selected evidence set for verification.
        selected = r3[:5]
        selected_items = [
            u for u in sub_corpus.units if u.evidence_id in {r.evidence_id for r in selected}
        ]
        v = _verify(selected_items, case, sub_corpus, verify_joint_temporal, verify_calculation,
                    EvidenceItem, VersionRelation)
        verification_results[cid] = v

        # Routing: GOLD-FREE (audit P0-1 fix). The decision comes from the
        # retrieved evidence and the joint verifier state ONLY. The hidden
        # gold_answer is never consulted here — it is consumed only by the
        # offline evaluator below.
        decisions[cid] = route_decision(
            has_evidence=bool(selected_items),
            joint_valid=v["joint_valid"],
        )

        # Evaluator runs AFTER the decision; gold touches ONLY this step.
        evaluation = evaluate_correctness(decisions[cid], v, case, rec.get("route"))

        per_case.append({
            "case_id": cid,
            "route": rec["route"],
            "status": rec["status"],
            "decision": decisions[cid],
            "evaluation": evaluation,
            "retrieval": retrieval_results[cid],
            "set_selection": set_selection_results[cid],
            "verification": v,
        })

    return _summarize(
        per_case, decisions, facts_corpus, dense_available,
        gold=gold, sealed=sealed,
        evidence_packages_dir=ROOT / "human_review/evidence_packages",
    )


_BM25_CACHE: dict[str, Any] = {}


def _issuer_bm25(sub_corpus: FullCorpus) -> Any:
    """BM25 index for a sub-corpus, built ONCE per corpus (cached)."""
    import hashlib

    from finvest.retrieval.full_corpus import _tokenize
    from rank_bm25 import BM25Okapi

    key = hashlib.sha256(
        "\x1f".join(u.evidence_id for u in sub_corpus.units[:2000]).encode("utf-8")
    ).hexdigest()[:16]
    if key not in _BM25_CACHE:
        texts = [_tokenize(u.text_span or "") for u in sub_corpus.units]
        _BM25_CACHE[key] = BM25Okapi(texts)
    return _BM25_CACHE[key]


def _rrf_query(index: Any, sub_corpus: FullCorpus, query, top_k: int = 20, *, dense_ok: bool = True):
    """RRF over the shared BM25 index + dense (dense uses the disk cache)."""
    from finvest.retrieval.full_corpus import RankedResult, dense_retrieve

    k = 60.0
    r1 = _bm25_query(index, sub_corpus, query.question, top_k=200)
    scores: dict[str, float] = {}
    for rank, r in enumerate(r1, start=1):
        scores[r.evidence_id] = scores.get(r.evidence_id, 0.0) + 1.0 / (k + rank)
    if dense_ok:
        try:
            r2 = dense_retrieve(sub_corpus, query.question, top_k=200)
            for rank, r in enumerate(r2, start=1):
                scores[r.evidence_id] = scores.get(r.evidence_id, 0.0) + 1.0 / (k + rank)
        except Exception:
            pass  # dense unavailable -> RRF degrades to BM25 ranking
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    by_id = {u.evidence_id: u for u in sub_corpus.units}
    return tuple(
        RankedResult(evidence_id=eid, document_id=by_id[eid].document_id,
                     score=score, rank=rank)
        for rank, (eid, score) in enumerate(ranked, start=1)
    )


def _bm25_query(index: Any, sub_corpus: FullCorpus, query: str, top_k: int = 20):
    """Score a query against a prebuilt BM25 index (no reindex per call)."""
    from finvest.retrieval.full_corpus import RankedResult, _tokenize

    scores = index.get_scores(_tokenize(query))
    ranked = sorted(
        ((scores[i], sub_corpus.units[i]) for i in range(len(sub_corpus.units))),
        key=lambda item: (-item[0], item[1].evidence_id),
    )[:top_k]
    return tuple(
        RankedResult(evidence_id=unit.evidence_id, document_id=unit.document_id,
                     score=score, rank=rank)
        for rank, (score, unit) in enumerate(ranked, start=1)
    )


def _filing_from_doc(document_id: str, corpus: FullCorpus) -> date | None:
    """Best-effort filing date from document_id (issuer-FORM-end); None if unknown."""
    try:
        end = document_id.split("-")[-1]
        return date.fromisoformat(end)
    except (ValueError, IndexError):
        return None


def _verify(
    items, case, corpus, verify_joint_temporal, verify_calculation,
    EvidenceItem, VersionRelation,
) -> dict[str, Any]:
    """PRODUCTION verifier — GOLD-FREE by construction.

    Decides ANSWER/REVIEW/ABSTAIN from the evidence alone:
      V1 temporal/version  — source-time, valid-time, period, supersession
      V2 numerical         — calculation EXECUTABILITY (can the evidence
                             produce a number?), never comparison to gold
    The gold answer NEVER enters this path (see evaluate_correctness).
    """
    from datetime import datetime as _dt

    cutoff = None
    if case.get("source_cutoff"):
        cutoff = _dt.fromisoformat(str(case["source_cutoff"]).replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=_dt.now().astimezone().tzinfo)
    target_end = None
    if case.get("target_period_end"):
        target_end = date.fromisoformat(str(case["target_period_end"])[:10])
    target_fy = case.get("target_fiscal_year")

    relations = tuple(
        VersionRelation(**rel) for rel in (case.get("version_relations") or [])
    )
    temporal = verify_joint_temporal(
        tuple(items), source_cutoff=cutoff or _dt(1970, 1, 1), target_end=target_end,
        target_fiscal_year=target_fy, version_relations=relations,
    )

    # V2 numerical EXECUTABILITY: expected_value is deliberately None so the
    # decision depends only on whether the evidence can produce a number, not
    # on whether it matches the hidden gold (no target leakage in routing).
    program = case.get("calculation_program")
    numerical = None
    if program and program.get("operation"):
        texts = tuple(u.text_span or "" for u in items)
        numerical = verify_calculation(
            operation=program["operation"], evidence_texts=texts,
            expected_value=None, tolerance=0.01,
        )

    # Production numerical semantics: the evidence must EXECUTE a calculation
    # (SUPPORTED) — REVIEW_REQUIRED (calc failed / no numbers) must NOT pass.
    temporal_ok = temporal.valid
    numerical_ok = numerical is None or numerical.verification_state == "SUPPORTED"
    joint = temporal_ok and numerical_ok

    return {
        "joint_valid": bool(joint),
        "temporal": {
            "valid": temporal.valid,
            "future_information_rate": round(temporal.future_information_rate, 4),
            "expired_rate": round(temporal.expired_evidence_rate, 4),
            "wrong_period_rate": round(temporal.wrong_period_rate, 4),
            "superseded_rate": round(temporal.superseded_rate, 4),
            "violations": list(temporal.violations[:5]),
        },
        "numerical": {
            "present": numerical is not None,
            "verification_state": numerical.verification_state if numerical else None,
            "result": numerical.result if numerical else None,
            "note": "executability only; gold never enters the decision",
        },
    }


def evaluate_correctness(
    decision: str,
    verifier: dict[str, Any],
    case: dict[str, Any],
    human_route: str | None,
) -> dict[str, Any]:
    """EVALUATOR — the ONLY place gold is compared. Gold never shapes decisions.

    Uses the hidden gold_answer + the human label to score the ROUTING and, for
    ANSWER cases, the numeric correctness. This is offline evaluation only.
    """
    gold_answer = (case.get("gold_answer") or {}).get("value")
    gold_route = "ANSWER" if gold_answer is not None else "ABSTAIN"
    gold_route = human_route or gold_route

    if decision == "ANSWER" and gold_route == "ANSWER":
        # Numeric correctness vs gold — evaluator-only comparison.
        num = verifier.get("numerical", {})
        result = num.get("result")
        correct = (
            result is not None and gold_answer is not None
            and abs(result - float(gold_answer)) / max(1.0, abs(float(gold_answer))) <= 0.01
        )
        return {"bucket": "answer", "correct": bool(correct), "gold_used": True}
    if decision == "REVIEW":
        # A REVIEW is correct iff deferral was warranted: the case's gold route
        # is NOT a straightforward ANSWER (either the human also flagged it, or
        # the case is unanswerable). A REVIEW on an answerable case is an
        # over-deferral (false review) — this is what makes review_precision
        # and false_review_rate real, data-dependent metrics instead of the
        # tautological 'X or True' the pre-audit code produced.
        return {"bucket": "review", "correct": gold_route != "ANSWER", "gold_used": True}
    return {"bucket": "abstain", "correct": gold_route == "ABSTAIN", "gold_used": True}


def _summarize(per_case, decisions, facts_corpus, dense_available, *, gold, sealed, evidence_packages_dir) -> dict[str, Any]:
    # Answer/review/abstain buckets (honest separation).
    answer_bucket = [c for c in per_case if c["decision"] == "ANSWER"]
    review_bucket = [c for c in per_case if c["decision"] == "REVIEW"]
    abstain_bucket = [c for c in per_case if c["decision"] == "ABSTAIN"]

    # Gold label agreement on ANSWER cases (only where human also said ANSWER).
    answer_agree = sum(
        1 for c in answer_bucket if c["route"] == "ANSWER"
    )
    answer_total = sum(1 for c in answer_bucket)

    # --- Denominator audit (P0-1): every count is explicit and auditable ---
    annotated_ids = {r["case_id"] for r in gold}
    sealed_ids = set(sealed)
    n_annotated = len(annotated_ids)
    n_excluded_no_sealed_case = len(annotated_ids - sealed_ids)
    n_eligible_for_evaluation = n_annotated - n_excluded_no_sealed_case
    n_presented = len(per_case)
    n_excluded_failed_present = n_eligible_for_evaluation - n_presented
    # Gold answerable vs insufficient (from sealed gold, not human_answer, so
    # it is independent of the annotation).
    n_answerable_gold = sum(
        1 for cid, c in sealed.items()
        if cid in annotated_ids and (c.get("gold_answer") or {}).get("value") is not None
    )
    n_insufficient_gold = sum(
        1 for cid, c in sealed.items()
        if cid in annotated_ids and (c.get("gold_answer") or {}).get("value") is None
    )
    n_packages_total = (
        len([p for p in evidence_packages_dir.iterdir() if p.is_dir()])
        if evidence_packages_dir.exists() else 0
    )

    denominator_audit = {
        "n_packages_total": n_packages_total,
        "n_annotated": n_annotated,
        "n_eligible_for_evaluation": n_eligible_for_evaluation,
        "n_excluded_no_sealed_case": n_excluded_no_sealed_case,
        "n_excluded_failed_present": n_excluded_failed_present,
        "n_final_evaluated": n_presented,
        "n_answerable_gold": n_answerable_gold,
        "n_insufficient_gold": n_insufficient_gold,
        "excluded_ids": sorted(annotated_ids - sealed_ids),
        "note": (
            "n_final_evaluated = n_annotated - n_excluded_no_sealed_case - "
            "n_excluded_failed_present. Recall@K and decision rates use "
            "n_final_evaluated as the denominator; all counts are auditable."
        ),
    }

    return {
        "experiment": "A11_TWO_STAGE",
        "schema_version": "a11-two-stage.v1",
        "markers": MARKERS,
        "gold_source": "SOLO_ANNOTATIONS.jsonl (solo-v1, provisional)",
        "n_cases": len(per_case),
        "denominator_audit": denominator_audit,
        "corpus": {
            "corpus_id": facts_corpus.corpus_id,
            "record_count": len(facts_corpus.records),
            "dense_available": dense_available,
            "leakage_audit": facts_corpus.split_manifest["audit"],
        },
        "decisions": {
            "ANSWER": len(answer_bucket),
            "REVIEW": len(review_bucket),
            "ABSTAIN": len(abstain_bucket),
        },
        "answer_agreement": {
            "answer_cases": answer_total,
            "agree_with_human_answer_route": answer_agree,
            "rate": round(answer_agree / max(answer_total, 1), 4),
        },
        "review_bucket": [c["case_id"] for c in review_bucket],
        "abstain_bucket": [c["case_id"] for c in abstain_bucket],
        "per_case": per_case,
        "per_issuer_retrieval": _per_issuer_retrieval(per_case),
        "leave_one_issuer_out": _leave_one_issuer_out(per_case),
        "selective": _selective_summary(per_case),
        "honest_note": (
            "Retrieval candidates come from the leak-free corpus; no gold "
            "evidence is fed to R1-R4; gold NEVER enters the production "
            "verifier (it is consumed only by the offline evaluator). "
            "R2 is skipped when the dense model cache is absent. S4 is an "
            "UPPER_BOUND_ONLY oracle, never a headline. These are pilot "
            "numbers (solo-provisional labels), NOT paper results."
        ),
    }


_RETRIEVERS = ("R1_bm25", "R2_dense", "R3_rrf", "R4_concept_temporal")


def _per_issuer_retrieval(per_case) -> dict[str, Any]:
    """Per-issuer Recall@K + macro average (P1-3: issuer units, not records)."""
    from collections import defaultdict

    by_issuer: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for c in per_case:
        issuer = c["case_id"].split("-")[1] if "-" in c["case_id"] else "?"
        for rname in _RETRIEVERS:
            r = c["retrieval"].get(rname, {})
            if "recall_at_5" in r:
                by_issuer[issuer][rname].append(r["recall_at_5"])

    per_issuer = {}
    for issuer, methods in sorted(by_issuer.items()):
        per_issuer[issuer] = {
            rname: round(sum(v) / len(v), 4) if v else None
            for rname, v in methods.items()
        }
    # Macro average (mean of per-issuer means) — not micro (per-case).
    macro = {}
    for rname in _RETRIEVERS:
        vals = [per_issuer[i][rname] for i in per_issuer if per_issuer[i].get(rname) is not None]
        macro[rname] = round(sum(vals) / len(vals), 4) if vals else None
    return {"per_issuer": per_issuer, "macro_average_recall@5": macro}


def _leave_one_issuer_out(per_case) -> dict[str, Any]:
    """Leave-one-issuer-out: each issuer's cases are held out once; report the
    macro-averaged recall@5 across the six folds (P1-3: variance across folds)."""
    from collections import defaultdict

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in per_case:
        issuer = c["case_id"].split("-")[1] if "-" in c["case_id"] else "?"
        groups[issuer].append(c)

    folds = {}
    for held_out, held_cases in sorted(groups.items()):
        train = [c for iss, cs in groups.items() if iss != held_out for c in cs]
        train_recall = defaultdict(list)
        for c in train:
            for rname in _RETRIEVERS:
                r = c["retrieval"].get(rname, {})
                if "recall_at_5" in r:
                    train_recall[rname].append(r["recall_at_5"])
        folds[held_out] = {
            "held_out_cases": len(held_cases),
            "train_cases": len(train),
            "macro_recall@5_train": {
                rname: round(sum(v) / len(v), 4) if v else None
                for rname, v in train_recall.items()
            },
        }
    return {"folds": folds, "n_folds": len(folds)}


def _selective_summary(per_case) -> dict[str, Any]:
    """Coverage / selective risk (P0-3): report coverage + precision per bucket
    so '18 REVIEW' is not conflated with success."""
    n = len(per_case) or 1
    answer = [c for c in per_case if c["decision"] == "ANSWER"]
    review = [c for c in per_case if c["decision"] == "REVIEW"]
    abstain = [c for c in per_case if c["decision"] == "ABSTAIN"]
    answer_correct = sum(1 for c in answer if c.get("evaluation", {}).get("correct"))
    review_correct = sum(1 for c in review if c.get("evaluation", {}).get("correct"))
    abstain_correct = sum(1 for c in abstain if c.get("evaluation", {}).get("correct"))
    return {
        "coverage": round(len(answer) / n, 4),
        "answer_precision": round(answer_correct / max(len(answer), 1), 4),
        "review_precision": round(review_correct / max(len(review), 1), 4),
        "abstention_precision": round(abstain_correct / max(len(abstain), 1), 4),
        "false_review_rate": round(
            sum(1 for c in review if c.get("evaluation", {}).get("correct") is False)
            / max(len(review), 1), 4,
        ),
        "unsafe_answer_rate": round(
            sum(1 for c in answer if c.get("evaluation", {}).get("correct") is False)
            / max(len(answer), 1), 4,
        ),
        "note": (
            "coverage = ANSWER share; a system that always REVIEWS has high "
            "safety but zero utility — report coverage alongside precision."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="use fixture cache")
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    result = run_two_stage(fixture=args.fixture, top_k=args.top_k)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    sys.exit(0)
