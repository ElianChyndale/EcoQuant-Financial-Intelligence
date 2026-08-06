"""Day-1 single-researcher human-validation pilot (bounded, honest).

Scope (NOT the full A9 human study, NOT a paper headline):
- 22 SEC base-case queue (candidate cases, human verification pending);
- 12 paired evidence-condition queue (stratified across 6 conditions);
- 5 blind within-reviewer repeat annotations;
- 9 single-reviewer interface usability cases (3 answer-only, 3 top-k
  pages, 3 structured evidence package);
- one leakage-free low-capacity VISTA-Fin exploratory training run, gated
  on human-verified labels;
- audit + claim-boundary reports.

Division of labour:
- AI prepares: candidate queues from the SEC XBRL case builder, freeze +
  SHA-256 hashes, empty human-signed record files, display-safe reviewer
  sheet, reliability-analysis pipeline, gated VISTA pilot runner.
- The human researcher fills and signs every record. AI NEVER generates,
  infers, fills, or modifies human labels, never displays candidate labels
  before a first-pass label is frozen, and never claims agreement or
  significance.

Honesty markers used throughout:
EXPLORATORY_PILOT · SMALL_SAMPLE · NOT_PAPER_HEADLINE ·
INSUFFICIENT_DATA_FOR_TRAINING
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from finvest.benchmark.builders.sec_cases import build_sec_cases
from finvest.benchmark.conditions import ConditionedInstance, generate_conditions
from finvest.benchmark.schemas import EvidenceItem, FinVestCase
from finvest.retrieval.full_corpus import bm25_retrieve, build_full_corpus
from finvest.set_selection.selectors import (
    CoverageModel,
    SelectedSet,
    b1_top_k,
    b2_greedy_set_cover,
    b3_beam_search,
    b4_ilp_oracle,
    set_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
DAY1_DIR = ROOT / "human_review/day1"
CACHE_DIR = ROOT / "research/cache"

# Frozen design constants (preregistered before any human label exists).
FREEZE_SEED = 20260806
BASE_TICKERS = ("AAPL", "MSFT", "KO", "EQIX", "JNJ", "UPS")
PAIRED_CONDITIONS = (
    "PARTIAL_MISSING_INPUT",
    "OUTDATED",
    "FUTURE_LEAK",
    "WRONG_PERIOD",
    "CONFLICTING",
    "DISTRACTOR",
)
PAIRED_PER_CONDITION = 2  # -> 12 paired instances
BLIND_REPEAT_SIZE = 5
INTERFACE_DISPLAY_CONDITIONS = ("answer_only", "answer_topk_pages", "answer_vista_package")
INTERFACE_PER_CONDITION = 3  # -> 9 interface cases
VISTA_SEEDS = (20260806, 20260807, 20260808)  # 3 seeds, frozen
VISTA_ELIGIBILITY = {"min_signed_labels": 12, "min_issuers": 3}

# One-line restatement of the non-negotiable rules for the audit trail.
POLICY_RULES = (
    "1. Never generate, infer, fill, or modify human labels.",
    "2. Never display candidate labels, system predictions, model scores, or "
    "prior annotations before the researcher's first-pass label is frozen.",
    "3. AI may validate schema and evidence-ID existence only.",
    "4. Human signatures require explicit researcher action.",
    "5. This work is a pilot, not a human study.",
    "6. No inter-rater agreement may be claimed (single reviewer).",
    "7. No statistical significance may be reported.",
    "8. Gold-derived values are never used as model inference features.",
    "9. No tuning on held-out issuer results.",
    "10. All unresolved and ambiguous cases are preserved.",
)

# Annotation fields required on every base/paired/blind-repeat record
# (exactly the field list from the day-1 pilot brief).
ANNOTATION_FIELDS = (
    "question_valid", "answerability", "sufficiency", "entity", "metric",
    "target_period", "unit_and_scale", "reporting_scope",
    "mandatory_requirements", "supporting_evidence_ids", "minimal_evidence_set",
    "source_time_valid", "version_valid", "calculation_reproducible",
    "final_answer_or_null", "reviewer_confidence", "reviewer_notes",
    "signed_by", "timestamp", "elapsed_seconds",
)
# A record is SIGNED iff signed_by is non-empty and timestamp is present;
# ``signed: true`` is an optional explicit acknowledgment on top of that.
SIGNATURE_FIELDS = ("signed_by", "timestamp")

PILOT_MARKERS = ("EXPLORATORY_PILOT", "SMALL_SAMPLE", "NOT_PAPER_HEADLINE")


def canonical_json(obj: Any) -> str:
    """Deterministic JSON string for stable hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Queue construction (deterministic; no human labels involved)
# ---------------------------------------------------------------------------

def build_base_queue(cache_dir: Path = CACHE_DIR) -> tuple[FinVestCase, ...]:
    """The 22 candidate SEC base cases (AI-generated; verification pending)."""
    built = build_sec_cases(cache_dir, tickers=BASE_TICKERS)
    if len(built.cases) < 22:
        raise RuntimeError(
            f"expected >= 22 candidate base cases, got {len(built.cases)}; "
            "cache may be incomplete"
        )
    for case in built.cases:
        case.validate()
    return tuple(built.cases)


def _case_evidence_qualifies(case: FinVestCase, condition: str) -> bool:
    """Whether generate_conditions can produce the condition for this case."""
    n_evidence = len(case.evidence_items)
    if condition == "PARTIAL_MISSING_INPUT":
        return n_evidence >= 2
    if condition in {"OUTDATED", "FUTURE_LEAK", "WRONG_PERIOD", "CONFLICTING", "DISTRACTOR"}:
        return n_evidence >= 1
    return False


def _distractor_pool_for(
    case: FinVestCase,
    all_items: tuple[EvidenceItem, ...],
) -> tuple[EvidenceItem, ...]:
    """Deterministic other-document distractor pool (inference-time only).

    Items come from evidence lists of OTHER documents, so they are
    semantically plausible but irrelevant to this case. For FUTURE_LEAK the
    first pool item is re-stamped to one day after the case's source cutoff
    with a neutral evidence-ID suffix; for DISTRACTOR the first two items are
    used as-is.
    """
    case_doc = {e.document_id for e in case.evidence_items}
    cross = sorted(
        (e for e in all_items if e.document_id not in case_doc),
        key=lambda e: (e.evidence_id, e.document_id),
    )
    if not cross:
        return ()
    leaked = cross[0]
    future = EvidenceItem(
        **{
            **asdict(leaked),
            "evidence_id": f"{leaked.evidence_id}.x",
            "filing_date": case.source_cutoff.date() + timedelta(days=1),
        }
    )
    return (future, *cross[1:])


def build_paired_queue(
    cases: tuple[FinVestCase, ...],
    seed: int = FREEZE_SEED,
) -> tuple[ConditionedInstance, ...]:
    """12 paired instances, stratified 2 per condition across 6 conditions."""
    all_items = tuple(e for case in cases for e in case.evidence_items)
    rng = random.Random(seed)
    instances: list[ConditionedInstance] = []
    for condition in PAIRED_CONDITIONS:
        qualifying = sorted(
            c.case_id for c in cases if _case_evidence_qualifies(c, condition)
        )
        if len(qualifying) < PAIRED_PER_CONDITION:
            raise RuntimeError(f"not enough qualifying cases for {condition}")
        offset = rng.randrange(len(qualifying))
        chosen = (qualifying[offset], qualifying[(offset + 1) % len(qualifying)])
        for case_id in chosen:
            case = next(c for c in cases if c.case_id == case_id)
            generated = generate_conditions(
                case, distractor_pool=_distractor_pool_for(case, all_items)
            )
            instance = next(i for i in generated if i.condition == condition)
            instances.append(instance)
    # Frozen order: stable sort, then assert stratification.
    instances.sort(key=lambda i: (i.condition, i.instance_id))
    conditions = [i.condition for i in instances]
    assert all(conditions.count(c) == PAIRED_PER_CONDITION for c in PAIRED_CONDITIONS)
    assert len(instances) == len(PAIRED_CONDITIONS) * PAIRED_PER_CONDITION
    return tuple(instances)


def select_blind_repeat(
    cases: tuple[FinVestCase, ...],
    seed: int = FREEZE_SEED,
    n: int = BLIND_REPEAT_SIZE,
) -> tuple[dict[str, str], ...]:
    """Deterministic blind-repeat selection: 5 cases, temp IDs, shuffled."""
    ids = sorted(c.case_id for c in cases)
    rng = random.Random(seed)
    chosen = rng.sample(ids, n)
    order = rng.sample(chosen, n)
    return tuple(
        {"temp_id": f"br-{i + 1:02d}", "case_id": case_id}
        for i, case_id in enumerate(order)
    )


def _candidate_answer(case: FinVestCase) -> dict[str, Any]:
    """AI candidate answer (sealed; never displayed before first pass)."""
    if case.answer_type == "unanswerable":
        return {"candidate": True, "value": None, "note": "ABSTAIN candidate"}
    return {"candidate": True, "value": case.gold_answer, "note": "AI candidate"}


def _top_k_pages(question: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Deterministic BM25 top-k pages over the cached full-corpus (sealed)."""
    corpus = build_full_corpus(CACHE_DIR)
    return [
        {"evidence_id": r.evidence_id, "document_id": r.document_id,
         "score": round(float(r.score), 6), "rank": r.rank}
        for r in bm25_retrieve(corpus, question, top_k=top_k)
    ]


def _vista_package(case: FinVestCase) -> dict[str, Any]:
    """Candidate VISTA evidence package (sealed; interface display content)."""
    requirements = []
    if case.requirement_graph is not None:
        requirements = [
            {"node_id": n.node_id, "node_type": n.node_type, "value": n.value}
            for n in case.requirement_graph.nodes
        ]
    minimal = sorted(case.minimal_evidence_sets[0]) if case.minimal_evidence_sets else []
    program = None
    if case.calculation_program is not None:
        program = {
            "operation": case.calculation_program.operation,
            "inputs": list(case.calculation_program.inputs),
            "result": case.calculation_program.result,
            "unit": case.calculation_program.unit,
            "scale": case.calculation_program.scale,
            "period": case.calculation_program.period,
        }
    return {
        "requirements": requirements,
        "minimal_evidence_set": minimal,
        "calculation_trace": program,
        "version_relations": [asdict(v) for v in case.version_relations],
        "known_conflicts": list(case.known_conflicts),
    }


def build_interface_cases(
    cases: tuple[FinVestCase, ...],
    seed: int = FREEZE_SEED,
) -> tuple[dict[str, Any], ...]:
    """9 interface cases: distinct base questions, 3 per display condition."""
    rng = random.Random(seed)
    conditions = list(
        INTERFACE_DISPLAY_CONDITIONS * INTERFACE_PER_CONDITION
    )  # 3 of each
    rng.shuffle(conditions)
    chosen: list[FinVestCase] = []
    seen_questions: set[str] = set()
    pool = list(cases)
    rng.shuffle(pool)
    for case in pool:
        if len(chosen) == len(conditions):
            break
        if case.base_question_id in seen_questions:
            continue
        chosen.append(case)
        seen_questions.add(case.base_question_id)
    if len(chosen) < len(conditions):
        raise RuntimeError("fewer than 9 distinct base questions available")
    result: list[dict[str, Any]] = []
    for case, condition in zip(chosen, conditions):
        bundle: dict[str, Any] = {"display_condition": condition}
        bundle["candidate_answer"] = _candidate_answer(case)
        if condition == "answer_topk_pages":
            bundle["top_k_pages"] = _top_k_pages(case.question)
        if condition == "answer_vista_package":
            bundle["vista_package"] = _vista_package(case)
        result.append({"case_id": case.case_id, "base_question_id": case.base_question_id,
                       **bundle})
    return tuple(result)


# ---------------------------------------------------------------------------
# Freeze + hash + empty human-record scaffolding
# ---------------------------------------------------------------------------

def _split_manifest(cases: tuple[FinVestCase, ...]) -> dict[str, Any]:
    """Leave-one-issuer-out folds; grouped by issuer and base question."""
    issuers = sorted({c.issuer_id for c in cases})
    return {
        "split": "leave_one_issuer_out",
        "grouping": "issuer + base_question (Levels 1 & 4 isolation)",
        "seeds": list(VISTA_SEEDS),
        "folds": [
            {"test_issuer": issuer,
             "train_issuers": [i for i in issuers if i != issuer]}
            for issuer in issuers
        ],
        "note": "No test tuning; thresholds fixed before evaluation.",
    }


def _experiment_config() -> dict[str, Any]:
    """Frozen experiment config for the gated VISTA pilot."""
    return {
        "method": "P1_low_capacity_logistic_selector",
        "baselines": ["b1_top_k", "b2_greedy_set_cover", "b3_beam_search", "b4_ilp_oracle"],
        "features": [
            "retrieval_score", "requirement_coverage_fraction", "temporal_flag",
            "conflict_flag", "execution_flag", "unit_match_flag",
            "period_overlap_flag", "text_length",
        ],
        "feature_provenance": "inference_time_only (no gold-derived values)",
        "metrics": [
            "all_required_evidence_recall", "evidence_set_precision",
            "false_support_rate", "wrong_period_rate", "minimality_violation",
            "average_set_size",
        ],
        "eligibility": VISTA_ELIGIBILITY,
        "eligibility_rule": (
            "train only after human labels are frozen; if fewer than the "
            "required labels/issuers, report INSUFFICIENT_DATA_FOR_TRAINING"
        ),
        "markers": list(PILOT_MARKERS),
        "no_test_tuning": True,
        "weak_paired_conditions_train_rule": (
            "weakly generated paired conditions may train only when their "
            "transformation is deterministic; headline evaluation uses "
            "human-verified cases only"
        ),
    }


def _reviewer_base_view(cases: tuple[FinVestCase, ...]) -> list[dict[str, Any]]:
    """Display-safe projection: questions + evidence descriptors, NO labels."""
    rows: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda c: c.case_id):
        rows.append({
            "case_id": case.case_id,
            "question": case.question,
            "evidence": [
                {"evidence_id": e.evidence_id, "document_id": e.document_id,
                 "document_version": e.document_version,
                 "filing_date": e.filing_date, "valid_from": e.valid_from,
                 "page_id": e.page_id, "section": e.section,
                 "table_id": e.table_id, "concept": e.concept, "unit": e.unit,
                 "scale": e.scale, "scope": e.scope}
                for e in case.evidence_items
            ],
            "source_files": ["research/cache/sec/companyfacts"],
        })
    return rows


def freeze_day1(
    seed: int = FREEZE_SEED,
    day1_dir: Path = DAY1_DIR,
) -> dict[str, Any]:
    """Build and freeze all queues; write manifest, hashes, empty records."""
    cases = build_base_queue()
    paired = build_paired_queue(cases, seed=seed)
    blind = select_blind_repeat(cases, seed=seed)
    interface = build_interface_cases(cases, seed=seed)
    split = _split_manifest(cases)
    config = _experiment_config()

    paired_rows, paired_token_map = _paired_reviewer_view(paired)
    sealed: dict[str, Any] = {
        "base_22_queue": [asdict(c) for c in cases],
        "paired_12_queue": [asdict(i) for i in paired],
        "paired_12_token_map": paired_token_map,
        "blind_repeat_5_selection": list(blind),
        "interface_9_cases": interface,
        "split_manifest": split,
        "experiment_config": config,
    }
    reviewer_view: dict[str, Any] = {
        "base_22": _reviewer_base_view(cases),
        "paired_12": paired_rows,
        "blind_repeat_5": [
            {"temp_id": r["temp_id"],
             "question": next(
                 c.question for c in cases if c.case_id == r["case_id"]
             )}
            for r in blind
        ],
        "interface_9": [
            {"case_id": i["case_id"], "display_condition": i["display_condition"],
             "question": next(
                 c.question for c in cases if c.case_id == i["case_id"]
             )}
            for i in interface
        ],
    }

    components = {
        name: sha256_hex(canonical_json(content))
        for name, content in sealed.items()
    }
    components["reviewer_view"] = sha256_hex(canonical_json(reviewer_view))
    # The annotation guideline is a frozen researcher-facing document; hash it
    # when present so any post-freeze edit is detected by ``verify_frozen``.
    guideline_path = day1_dir / "ANNOTATION_GUIDELINE.md"
    if guideline_path.exists():
        components["annotation_guideline"] = sha256_hex(
            guideline_path.read_text(encoding="utf-8")
        )
    total = sha256_hex(canonical_json(components))

    manifest: dict[str, Any] = {
        "manifest_id": "day1-human-validation-pilot",
        "manifest_version": "0.1.0",
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "freeze_seed": seed,
        "policy_rules": list(POLICY_RULES),
        "status": {
            "human_labels": "PENDING_HUMAN_LABEL",
            "signed": False,
            "note": "No human label exists until a record is filled, signed, "
                    "and timestamped by the researcher.",
        },
        "components": components,
        "total_sha256": total,
        "sealed": sealed,
        "reviewer_view": reviewer_view,
    }

    day1_dir.mkdir(parents=True, exist_ok=True)
    (day1_dir / "QUEUE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (day1_dir / "FROZEN.sha256").write_text(
        "".join(f"{sha}  {name}\n" for name, sha in sorted(components.items()))
        + f"{total}  TOTAL\n",
        encoding="utf-8",
    )
    _write_reviewer_sheet(reviewer_view, day1_dir)
    _write_empty_human_records(day1_dir)
    return manifest


def _write_reviewer_sheet(reviewer_view: dict[str, Any], day1_dir: Path) -> None:
    """Display-safe reviewer sheet (no candidate labels, no conditions).

    This is the ONLY sanctioned display surface for annotation. The sealed
    sections of QUEUE_MANIFEST.json must stay closed until the researcher's
    first-pass labels are frozen (policy rule 2).
    """
    lines = [
        "# Day-1 Reviewer Sheet (display-safe)",
        "",
        "Annotation surface for the day-1 pilot. Candidate answers, system",
        "scores, gold labels, and condition identities are NOT shown here.",
        "See ANNOTATION_GUIDELINE.md before starting.",
        "",
        "## 22 base cases (first pass)",
        "",
        "| Case ID | Question | Evidence (id · document · concept · period) |",
        "|---|---|---|",
    ]
    for row in reviewer_view["base_22"]:
        evidence = "; ".join(
            f"{e['evidence_id']} · {e['document_id']} · {e.get('concept')} · "
            f"{e.get('valid_from')}"
            for e in row["evidence"]
        ) or "(no evidence descriptor provided — verify against SEC source)"
        lines.append(f"| {row['case_id']} | {row['question']} | {evidence} |")
    lines += ["", "## 12 paired cases (condition identity hidden)", ""]
    lines.append("| Token | Question | Evidence (id · document · concept · period) |")
    lines.append("|---|---|---|")
    for row in reviewer_view["paired_12"]:
        evidence = "; ".join(
            f"{e['evidence_id']} · {e['document_id']} · {e.get('concept')} · "
            f"{e.get('valid_from')}"
            for e in row["evidence"]
        )
        lines.append(f"| {row['review_token']} | {row['question']} | {evidence} |")
    lines += ["", "## 5 blind repeats (second pass, temp IDs)", ""]
    lines.append("| Temp ID | Question |")
    lines.append("|---|---|")
    for row in reviewer_view["blind_repeat_5"]:
        lines.append(f"| {row['temp_id']} | {row['question']} |")
    lines += ["", "## 9 interface-pilot cases (display condition IS shown)", ""]
    lines.append("| Case ID | Display condition | Question |")
    lines.append("|---|---|---|")
    for row in reviewer_view["interface_9"]:
        lines.append(
            f"| {row['case_id']} | {row['display_condition']} | {row['question']} |"
        )
    lines.append("")
    (day1_dir / "REVIEWER_SHEET.md").write_text("\n".join(lines), encoding="utf-8")


def _paired_reviewer_view(
    paired: tuple[ConditionedInstance, ...],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Randomized order with neutral review tokens; condition hidden.

    The generator's ``instance_id`` embeds the condition name, so the reviewer
    sees only a ``pr-XX`` token; the token -> instance_id map is sealed in the
    manifest (never displayed before first-pass labels freeze).
    """
    rng = random.Random(FREEZE_SEED + 1)
    rows = [
        {
            "question": i.question,
            "evidence": [
                {"evidence_id": e.evidence_id, "document_id": e.document_id,
                 "document_version": e.document_version,
                 "filing_date": e.filing_date, "valid_from": e.valid_from,
                 "concept": e.concept, "unit": e.unit, "scale": e.scale}
                for e in i.evidence_items
            ],
            "condition_identity": "HIDDEN_DURING_REVIEW",
        }
        for i in paired
    ]
    rng.shuffle(rows)
    rows_out: list[dict[str, Any]] = []
    token_map: dict[str, str] = {}
    for index, (row, instance) in enumerate(zip(rows, paired)):
        token = f"pr-{index + 1:02d}"
        token_map[token] = instance.instance_id
        rows_out.append({"review_token": token, **row})
    return rows_out, token_map


def _write_empty_human_records(day1_dir: Path) -> None:
    """Empty JSONL files: zero human records exist until the researcher signs."""
    for name in (
        "BASE_22_HUMAN_SIGNED.jsonl",
        "PAIRED_12_HUMAN_SIGNED.jsonl",
        "BLIND_REPEAT_5.jsonl",
        "INTERFACE_PILOT_9.jsonl",
    ):
        path = day1_dir / name
        path.touch(exist_ok=True)
        if path.stat().st_size != 0:
            raise RuntimeError(f"refusing to overwrite non-empty human record file: {name}")


def verify_frozen(day1_dir: Path = DAY1_DIR) -> dict[str, Any]:
    """Recompute hashes from the frozen manifest; return violations."""
    manifest = json.loads((day1_dir / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    violations: list[str] = []
    for name, expected in manifest["components"].items():
        if name == "reviewer_view":
            content = manifest["reviewer_view"]
        elif name == "annotation_guideline":
            guideline = day1_dir / "ANNOTATION_GUIDELINE.md"
            content = (
                guideline.read_text(encoding="utf-8") if guideline.exists() else None
            )
        else:
            content = manifest["sealed"][name]
        if content is None:
            actual = "MISSING"
        elif isinstance(content, str):
            actual = sha256_hex(content)  # raw text, matching freeze-time hash
        else:
            actual = sha256_hex(canonical_json(content))
        if actual != expected:
            violations.append(f"{name}: hash mismatch")
    actual_total = sha256_hex(canonical_json(manifest["components"]))
    if actual_total != manifest["total_sha256"]:
        violations.append("total: hash mismatch")
    return {
        "manifest_id": manifest["manifest_id"],
        "frozen_at": manifest["frozen_at"],
        "status": manifest["status"],
        "violations": violations,
        "verified": not violations,
        "components_checked": len(manifest["components"]),
    }


# ---------------------------------------------------------------------------
# Intra-rater reliability (descriptive only; runs after BOTH passes frozen)
# ---------------------------------------------------------------------------

def cohen_kappa(ratings: list[tuple[str, str]]) -> dict[str, Any]:
    """Cohen's kappa for two raters on paired categorical labels.

    SMALL-SAMPLE WARNING: with the pilot's n=5 blind repeats, kappa is
    unstable; report descriptive agreement alongside, and never claim
    statistical significance (policy rule 7).
    """
    n = len(ratings)
    if n == 0:
        return {"n": 0, "kappa": None, "p0": None, "pe": None,
                "warning": "no paired ratings"}
    labels = sorted({a for pair in ratings for a in pair})
    n_label = len(labels)
    if n_label == 0:
        return {"n": n, "kappa": None, "p0": None, "pe": None,
                "warning": "no labels observed"}
    observed = [[0] * n_label for _ in range(n_label)]
    index = {label: i for i, label in enumerate(labels)}
    for a, b in ratings:
        observed[index[a]][index[b]] += 1
    p0 = sum(observed[i][i] for i in range(n_label)) / n
    row = [sum(observed[i]) for i in range(n_label)]
    col = [sum(observed[j][i] for j in range(n_label)) for i in range(n_label)]
    pe = sum(row[i] * col[i] for i in range(n_label)) / (n * n)
    if pe == 1.0:
        kappa = 1.0 if p0 == 1.0 else 0.0
    else:
        kappa = (p0 - pe) / (1.0 - pe)
    return {
        "n": n,
        "kappa": round(kappa, 4),
        "p0": round(p0, 4),
        "pe": round(pe, 4),
        "small_sample_warning": (
            n < 30 and "n below 30: kappa is unstable; report descriptive "
            "agreement, do not claim significance"
        ) or None,
    }


def evidence_jaccard(sets_a: list[set[str]], sets_b: list[set[str]]) -> dict[str, Any]:
    """Mean pairwise Jaccard similarity over evidence sets (aligned lists)."""
    if len(sets_a) != len(sets_b) or not sets_a:
        return {"n": 0, "mean_jaccard": None, "warning": "aligned non-empty lists required"}
    scores = []
    for a, b in zip(sets_a, sets_b):
        union = a | b
        scores.append(len(a & b) / len(union) if union else 1.0)
    return {
        "n": len(scores),
        "mean_jaccard": round(sum(scores) / len(scores), 4),
        "per_pair_jaccard": [round(s, 4) for s in scores],
    }


def numeric_agreement(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
    """Numeric agreement: both None (both abstain) agree; else relative tol."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        a_num, b_num = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
    if a_num == 0.0 and b_num == 0.0:
        return True
    return abs(a_num - b_num) / max(abs(a_num), abs(b_num), 1e-12) <= tolerance


def compute_intra_rater(
    base_records: list[dict[str, Any]],
    blind_records: list[dict[str, Any]],
    selection: list[dict[str, str]],
) -> dict[str, Any]:
    """Descriptive within-reviewer reliability: base pass-1 vs blind pass-2.

    Pass 1 = the researcher's signed base annotation of the case
    (BASE_22_HUMAN_SIGNED.jsonl). Pass 2 = the blind re-annotation under the
    temporary ID (BLIND_REPEAT_5.jsonl, ``pass: 2``). Pairs join via the
    frozen selection map (``temp_id -> case_id``); a pair exists only when
    both records are signed.

    Reports: categorical agreement, Cohen's kappa with a small-sample
    warning, evidence-set Jaccard, entity/period/unit agreement, numeric
    agreement. Never revise labels to increase agreement.
    """
    base_by_case: dict[str, dict[str, Any]] = {}
    for rec in base_records:
        if rec.get("signed_by") and rec.get("timestamp") and rec.get("case_id"):
            base_by_case[rec["case_id"]] = rec  # last record wins
    blind_by_temp: dict[str, dict[str, Any]] = {}
    for rec in blind_records:
        if rec.get("signed_by") and rec.get("timestamp") and rec.get("temp_id"):
            blind_by_temp[rec["temp_id"]] = rec
    paired: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in selection:
        p0 = base_by_case.get(row.get("case_id", ""))
        p1 = blind_by_temp.get(row.get("temp_id", ""))
        if p0 is not None and p1 is not None:
            paired.append((p0, p1))
    if not paired:
        return {
            "n_paired": 0,
            "status": "NO_DATA",
            "note": "the signed base record and the signed blind pass-2 record "
                    "must both exist for at least one of the 5 selected cases "
                    "before reliability can be computed",
        }

    final_answer_pairs = [
        (str(p0.get("final_answer_or_null")), str(p1.get("final_answer_or_null")))
        for p0, p1 in paired
    ]
    kappa = cohen_kappa(final_answer_pairs)

    def _field_agreement(field: str) -> float:
        agree = sum(1 for p0, p1 in paired if p0.get(field) == p1.get(field))
        return agree / len(paired)

    return {
        "n_paired": len(paired),
        "categorical_agreement": round(
            sum(1 for a, b in final_answer_pairs if a == b) / len(paired), 4
        ),
        "cohens_kappa": kappa,
        "evidence_set_jaccard": evidence_jaccard(
            [set(p0.get("supporting_evidence_ids") or []) for p0, _ in paired],
            [set(p1.get("supporting_evidence_ids") or []) for _, p1 in paired],
        ),
        "entity_agreement": round(_field_agreement("entity"), 4),
        "period_agreement": round(_field_agreement("target_period"), 4),
        "unit_agreement": round(_field_agreement("unit_and_scale"), 4),
        "numeric_agreement": round(
            sum(1 for p0, p1 in paired
                if numeric_agreement(p0.get("final_answer_or_null"),
                                     p1.get("final_answer_or_null")))
            / len(paired), 4,
        ),
        "markers": list(PILOT_MARKERS),
        "note": "descriptive only; no inter-rater or significance claim "
                "(single reviewer, n=5)",
    }


# ---------------------------------------------------------------------------
# Gated VISTA-Fin exploratory pilot (train ONLY after human labels freeze)
# ---------------------------------------------------------------------------

def predict_coverage(
    evidence: EvidenceItem,
    requirement_nodes: list[dict[str, Any]],
) -> frozenset[str]:
    """Inference-time predicted evidence->requirement coverage.

    Heuristic matchers over descriptor fields (concept/unit/scale/period/
    entity). No gold input. Used by B2/B3 baselines and P1 features.
    """
    covered: set[str] = set()
    doc_prefix = evidence.document_id.split("-")[0].upper()
    for node in requirement_nodes:
        node_id, node_type, value = node["node_id"], node["node_type"], node.get("value")
        if value is None:
            continue
        if node_type == "ENTITY" and doc_prefix == str(value).upper():
            covered.add(node_id)
        elif node_type in {"METRIC", "INTERMEDIATE_VALUE"} and evidence.concept == value:
            covered.add(node_id)
        elif node_type == "PERIOD" and evidence.valid_from is not None \
                and str(evidence.valid_from.year) == str(value):
            covered.add(node_id)
        elif node_type == "UNIT" and evidence.unit == value:
            covered.add(node_id)
        elif node_type == "SCALE" and evidence.scale == value:
            covered.add(node_id)
    return frozenset(covered)


def build_inference_features(
    retrieval_score: float,
    coverage: frozenset[str],
    total_requirements: int,
    temporal_flag: float,
    conflict_flag: float,
    execution_flag: float,
    unit_match_flag: float,
    period_overlap_flag: float,
    text_length: float,
) -> list[float]:
    """P1 feature vector: inference-time only (policy rules 8/9)."""
    coverage_fraction = (
        len(coverage) / total_requirements if total_requirements else 0.0
    )
    return [
        retrieval_score, coverage_fraction, temporal_flag, conflict_flag,
        execution_flag, unit_match_flag, period_overlap_flag, text_length,
    ]


class LowCapacityLogistic:
    """Pure-Python low-capacity logistic selector (P1), seeded and tiny.

    Batch gradient descent with L2 penalty. Low capacity by construction
    (single layer, no features beyond the frozen 8). Deterministic given seed.
    """

    def __init__(self, seed: int, lr: float = 0.1, epochs: int = 200, l2: float = 1e-4) -> None:
        self.rng = random.Random(seed)
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.weights: list[float] = []
        self.bias = 0.0

    def fit(self, x: list[list[float]], y: list[float]) -> None:
        n_dim = len(x[0]) if x else 0
        if n_dim == 0:
            raise ValueError("no features to fit")
        self.weights = [self.rng.gauss(0.0, 0.01) for _ in range(n_dim)]
        self.bias = 0.0
        for _ in range(self.epochs):
            grads = [0.0] * n_dim
            grad_bias = 0.0
            for row, label in zip(x, y):
                logit = self.bias + sum(w * v for w, v in zip(self.weights, row))
                prob = 1.0 / (1.0 + math.exp(-logit))
                error = prob - label
                for d in range(n_dim):
                    grads[d] += error * row[d]
                grad_bias += error
            for d in range(n_dim):
                self.weights[d] -= self.lr * (grads[d] / len(x) + self.l2 * self.weights[d])
            self.bias -= self.lr * grad_bias / len(x)

    def predict_proba(self, x: list[float]) -> float:
        logit = self.bias + sum(w * v for w, v in zip(self.weights, x))
        return 1.0 / (1.0 + math.exp(-logit))


def _metric_functions() -> dict[str, str]:
    """Frozen metric definitions for the pilot (documented, not gold-derived)."""
    return {
        "all_required_evidence_recall": (
            "|selected ∩ human_supported| / |human_supported| (reuses "
            "set_metrics; human_supported = researcher-signed "
            "supporting_evidence_ids)"
        ),
        "evidence_set_precision": (
            "|selected ∩ human_supported| / |selected| (set_metrics)"
        ),
        "false_support_rate": (
            "|selected \\ (human_supported ∪ period/version-valid)| / |selected|"
        ),
        "wrong_period_rate": (
            "|selected with valid_from outside target period| / |selected|"
        ),
        "minimality_violation": "set_metrics minimality_violation_rate",
        "average_set_size": "mean |selected| (set_metrics)",
    }


def _select_for_case(
    method: str,
    ranked_ids: list[str],
    requirements: frozenset[str],
    coverage: CoverageModel,
    gold_coverage: CoverageModel,
    k: int = 5,
) -> SelectedSet:
    if method == "b1_top_k":
        return b1_top_k(ranked_ids, k=k)
    if method == "b2_greedy_set_cover":
        return b2_greedy_set_cover(ranked_ids, requirements, coverage)
    if method == "b3_beam_search":
        return b3_beam_search(ranked_ids, requirements, coverage)
    if method == "b4_ilp_oracle":
        return b4_ilp_oracle(ranked_ids, requirements, gold_coverage)
    raise ValueError(f"unknown method: {method}")


def run_vista_pilot(
    day1_dir: Path = DAY1_DIR,
    output_path: Path = ROOT / "artifacts/results/VISTA_PILOT_V0_1.json",
) -> dict[str, Any]:
    """Gated exploratory pilot. Honest INSUFFICIENT_DATA when labels missing.

    Eligibility (frozen): >= 12 human-signed base labels spanning >= 3
    issuers. Headline evaluation uses human-verified cases only.
    """
    manifest = json.loads((day1_dir / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    config = manifest["sealed"]["experiment_config"]
    signed = _load_signed_records(day1_dir / "BASE_22_HUMAN_SIGNED.jsonl")
    issuers = {_issuer_of(rec["case_id"]) for rec in signed}
    n_labels = len(signed)
    n_issuers = len(issuers)
    required_labels = config["eligibility"]["min_signed_labels"]
    required_issuers = config["eligibility"]["min_issuers"]

    base_payload: dict[str, Any] = {
        "experiment": "VISTA_PILOT_V0_1",
        "markers": list(PILOT_MARKERS),
        "config": config,
        "metric_definitions": _metric_functions(),
        "human_verified_label_count": n_labels,
        "human_verified_issuer_count": n_issuers,
    }
    if n_labels < required_labels or n_issuers < required_issuers:
        base_payload.update({
            "status": "INSUFFICIENT_DATA_FOR_TRAINING",
            "reason": (
                f"human-verified labels frozen: {n_labels} across {n_issuers} "
                f"issuers; required: >= {required_labels} labels across >= "
                f"{required_issuers} issuers. Training is skipped honestly."
            ),
            "result": None,
        })
    else:
        base_payload.update({
            "status": "EXPLORATORY_PILOT_RUN",
            "result": _run_exploratory_pilot(signed, config),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(base_payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    # Tracked registry mirror (artifacts/ is gitignored by convention).
    mirror = ROOT / "research/results/vista_pilot_v0_1.json"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(
        json.dumps(base_payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return base_payload


def _load_signed_records(path: Path) -> list[dict[str, Any]]:
    """Load only explicitly signed records; silently skip empty/unsigned.

    A record is signed iff the researcher set ``signed_by`` (non-empty) and
    ``timestamp``. ``signed: true`` alone is NOT a signature.
    """
    if not path.exists():
        return []
    signed: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("signed_by") and rec.get("timestamp"):
            signed.append(rec)
    return signed


def _issuer_of(case_id: str) -> str:
    parts = case_id.split("-")
    for part in parts:
        if part.isupper() and len(part) >= 2:
            return part
    return "UNKNOWN"


def _mandatory_requirement_ids(case: dict[str, Any]) -> frozenset[str]:
    """Mandatory requirement node ids (same set as the VISTA scaffold)."""
    graph = case.get("requirement_graph") or {}
    return frozenset(
        n["node_id"] for n in graph.get("nodes", [])
        if n.get("node_type") in {"ENTITY", "METRIC", "PERIOD", "INTERMEDIATE_VALUE"}
    )


def _target_year(case: dict[str, Any]) -> int | None:
    """Fiscal year from target_period_end (for wrong-period detection)."""
    end = case.get("target_period_end")
    if end is None:
        return None
    try:
        return int(str(end).split("-")[0])
    except (TypeError, ValueError):
        return None


def _unit_context_flags(case: dict[str, Any], unit: EvidenceItem) -> dict[str, float]:
    """Inference-time flags for one (case, unit) pair (no gold input)."""
    cutoff = case.get("source_cutoff")
    cutoff_date = None
    if cutoff is not None:
        try:
            cutoff_date = date.fromisoformat(str(cutoff).split("T")[0])
        except ValueError:
            cutoff_date = None
    temporal = 1.0 if (
        unit.valid_from is not None
        and (cutoff_date is None or unit.valid_from <= cutoff_date)
    ) else 0.0
    year = _target_year(case)
    period_overlap = 1.0 if (
        year is not None and unit.valid_from is not None
        and unit.valid_from.year == year
    ) else 0.0
    conflict = 1.0 if case.get("known_conflicts") or case.get("version_relations") else 0.0
    execution = 1.0 if case.get("calculation_program") is not None else 0.0
    metric_values = {
        n.get("value") for n in (case.get("requirement_graph") or {}).get("nodes", [])
        if n.get("node_type") in {"METRIC", "INTERMEDIATE_VALUE"}
    }
    unit_match = 1.0 if unit.concept in metric_values else 0.0
    return {
        "temporal_flag": temporal,
        "conflict_flag": conflict,
        "execution_flag": execution,
        "unit_match_flag": unit_match,
        "period_overlap_flag": period_overlap,
    }


def _features_for(
    case: dict[str, Any],
    unit: EvidenceItem,
    retrieval_score: float,
    requirements: frozenset[str],
) -> list[float]:
    """Inference-time P1 features for one (case, unit, score) triple."""
    node_dicts = (case.get("requirement_graph") or {}).get("nodes", [])
    flags = _unit_context_flags(case, unit)
    return build_inference_features(
        retrieval_score=retrieval_score,
        coverage=predict_coverage(unit, node_dicts),
        total_requirements=len(requirements),
        temporal_flag=flags["temporal_flag"],
        conflict_flag=flags["conflict_flag"],
        execution_flag=flags["execution_flag"],
        unit_match_flag=flags["unit_match_flag"],
        period_overlap_flag=flags["period_overlap_flag"],
        text_length=float(len(unit.text_span or "")),
    )


def _select_p1(
    model: LowCapacityLogistic,
    scored_units: list[tuple[EvidenceItem, float]],
    case: dict[str, Any],
    requirements: frozenset[str],
    coverage: CoverageModel,
    max_size: int = 6,
) -> SelectedSet:
    """P1: rank units by learned probability, greedy-cover requirements."""
    scored: list[tuple[float, str]] = []
    for unit, score in scored_units:
        features = _features_for(case, unit, score, requirements)
        scored.append((model.predict_proba(features), unit.evidence_id))
    scored.sort(reverse=True)
    selected: list[str] = []
    remaining = set(requirements)
    for _, eid in scored:
        if len(selected) >= max_size or not remaining:
            break
        newly = coverage.coverage.get(eid, frozenset()) & remaining
        if not newly:
            continue
        selected.append(eid)
        remaining -= newly
    return SelectedSet(
        tuple(selected), method="p1_low_capacity",
        covered_requirements=frozenset(requirements) - remaining,
    )


def _unit_supports(
    unit: EvidenceItem,
    gold_support: frozenset[str],
    case: dict[str, Any],
    target_year: int | None,
) -> bool:
    """Per-unit support definition (frozen in the config's metric_definitions).

    Supporting = human-signed support, OR (period-valid AND version-valid).
    Period-valid: valid_from year matches the target fiscal year.
    Version-valid: the case has no unresolved known conflicts.
    """
    if unit.evidence_id in gold_support:
        return True
    period_ok = (
        unit.valid_from is not None
        and target_year is not None
        and unit.valid_from.year == target_year
    )
    version_ok = not case.get("known_conflicts")
    return period_ok and version_ok


def _evaluate_methods_on_cases(
    cases: list[dict[str, Any]],
    gold_by_case: dict[str, dict[str, Any]],
    corpus: Any,
    seed: int,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run B1-B4 + P1 on each case; return per-case metric records.

    ``corpus`` is a FullCorpus-like object (units with text_span +
    evidence_id). ``gold_by_case`` maps case_id -> signed record. B4 uses
    gold coverage (oracle upper bound; never headline). P1 uses the model
    fitted on train folds (``config["_fitted_model"]``).
    """
    records: list[dict[str, Any]] = []
    for case in cases:
        gold = gold_by_case.get(case["case_id"])
        if gold is None:
            continue
        requirements = _mandatory_requirement_ids(case)
        unit_map = {u.evidence_id: u for u in corpus.units}
        ranked = bm25_retrieve(corpus, case["question"], top_k=30)
        ranked_ids = [r.evidence_id for r in ranked]
        scores = {r.evidence_id: r.score for r in ranked}
        node_dicts = (case.get("requirement_graph") or {}).get("nodes", [])
        coverage = CoverageModel({
            eid: predict_coverage(unit, node_dicts)
            for eid, unit in unit_map.items()
        })
        gold_support = frozenset(gold.get("supporting_evidence_ids") or [])
        gold_minimal = frozenset(gold.get("minimal_evidence_set") or []) or gold_support
        gold_coverage = CoverageModel({
            eid: frozenset(requirements) if eid in gold_support else frozenset()
            for eid in unit_map
        })
        selections = {
            method: _select_for_case(
                method, ranked_ids, requirements, coverage, gold_coverage, k=5,
            )
            for method in config["baselines"]
        }
        model = config.get("_fitted_model")
        if model is not None:
            selections["p1_low_capacity"] = _select_p1(
                model,
                [(unit_map[eid], scores.get(eid, 0.0))
                 for eid in ranked_ids if eid in unit_map],
                case, requirements, coverage,
            )
        target_year = _target_year(case)
        row: dict[str, Any] = {"case_id": case["case_id"]}
        for method, selection in selections.items():
            metrics = set_metrics(selection, gold_support, gold_minimal,
                                  requirements, coverage)
            selected_ids = set(selection.evidence_ids)
            selected_units = [u for eid in selected_ids if (u := unit_map.get(eid))]
            wrong_period = sum(
                1 for u in selected_units
                if u.valid_from is None or target_year is None
                or u.valid_from.year != target_year
            ) / len(selected_units) if selected_units else 0.0
            false_support = sum(
                1 for u in selected_units
                if not _unit_supports(u, gold_support, case, target_year)
            ) / len(selected_units) if selected_units else 0.0
            row[method] = {
                "all_required_evidence_recall": metrics["all_required_evidence_recall"],
                "evidence_set_precision": metrics["set_precision"],
                "false_support_rate": false_support,
                "wrong_period_rate": wrong_period,
                "minimality_violation": metrics["minimality_violation_rate"],
                "average_set_size": metrics["average_set_size"],
            }
        records.append(row)
    return records


def _run_fold(
    train_gold: list[dict[str, Any]],
    test_cases: list[dict[str, Any]],
    gold_by_case: dict[str, dict[str, Any]],
    corpus: Any,
    seed: int,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """One leave-one-issuer-out fold: fit P1 on train, evaluate on test.

    Training pairs: supported units (y=1) and equally many top-ranked
    unsupported units (y=0) — deterministic, seeded, inference-time features
    only. No tuning on the held-out issuer (policy rule 9).
    """
    model = LowCapacityLogistic(seed=seed)
    rng = random.Random(seed)
    x: list[list[float]] = []
    y: list[float] = []
    for case in train_gold:
        gold = gold_by_case[case["case_id"]]
        supported = set(gold.get("supporting_evidence_ids") or [])
        requirements = _mandatory_requirement_ids(case)
        unit_map = {u.evidence_id: u for u in corpus.units}
        ranked = bm25_retrieve(corpus, case["question"], top_k=30)
        positives = [(r, unit_map[r.evidence_id]) for r in ranked
                     if r.evidence_id in supported and r.evidence_id in unit_map]
        negatives = [(r, unit_map[r.evidence_id]) for r in ranked
                     if r.evidence_id not in supported and r.evidence_id in unit_map]
        rng.shuffle(negatives)
        negatives = negatives[:max(len(positives), 8)]
        for r, unit in positives:
            x.append(_features_for(case, unit, r.score, requirements))
            y.append(1.0)
        for r, unit in negatives:
            x.append(_features_for(case, unit, r.score, requirements))
            y.append(0.0)
    if len(x) >= 2:
        model.fit(x, y)
    fold_config = dict(config)
    fold_config["_fitted_model"] = model
    return _evaluate_methods_on_cases(test_cases, gold_by_case, corpus, seed, fold_config)


def _run_exploratory_pilot(
    signed: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Leave-one-issuer-out x 3 seeds; grouped by issuer + base question.

    Runs only when eligibility passed. P1 trains on human-signed supporting
    evidence; baselines B1-B4 use predicted/gold coverage (B4 is an ORACLE
    upper bound and is never a headline result). No test tuning (rule 9).
    """
    manifest = json.loads((DAY1_DIR / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))
    cases = manifest["sealed"]["base_22_queue"]
    gold_by_case = {rec["case_id"]: rec for rec in signed}
    corpus = build_full_corpus(CACHE_DIR)

    per_seed: dict[str, Any] = {}
    all_records: list[dict[str, Any]] = []
    issuers = sorted({_issuer_of(c["case_id"]) for c in cases})
    for seed in config["seeds"]:
        seed_records: list[dict[str, Any]] = []
        for test_issuer in issuers:
            test_cases = [
                c for c in cases if _issuer_of(c["case_id"]) == test_issuer
                and c["case_id"] in gold_by_case
            ]
            train_gold = [
                gold_by_case[c["case_id"]] for c in cases
                if _issuer_of(c["case_id"]) != test_issuer
                and c["case_id"] in gold_by_case
            ]
            if not test_cases or not train_gold:
                continue
            seed_records.extend(
                _run_fold(train_gold, test_cases, gold_by_case, corpus, seed, config)
            )
        all_records.extend(seed_records)
        per_seed[f"seed_{seed}"] = seed_records

    methods = list(config["baselines"]) + ["p1_low_capacity"]
    metric_names = list(config["metrics"])
    aggregated: dict[str, dict[str, Any]] = {}
    for method in methods:
        aggregated[method] = {}
        for metric in metric_names:
            values = [
                float(r[method][metric]) for r in all_records
                if method in r and metric in r[method]
            ]
            if not values:
                aggregated[method][metric] = 0.0
                continue
            mean = sum(values) / len(values)
            sd = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
            aggregated[method][metric] = {
                "mean": round(mean, 4), "sd": round(sd, 4), "n": len(values),
            }
    return {
        "folds": [{"test_issuer": i} for i in issuers],
        "seeds_run": list(config["seeds"]),
        "per_seed": {k: len(v) for k, v in per_seed.items()},
        "aggregated": aggregated,
        "oracle_note": "b4_ilp_oracle uses gold coverage: upper bound only, "
                       "never a headline result (policy: oracle-conditioned)",
        "exploratory_note": (
            "EXPLORATORY_PILOT · SMALL_SAMPLE · NOT_PAPER_HEADLINE — "
            "no statistical significance claimed"
        ),
    }
