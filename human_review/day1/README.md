# human_review/day1 — Single-Researcher Validation Pilot

Status at freeze (2026-08-06): **PREPARATION COMPLETE · HUMAN LABELS
PENDING**. Nothing in this directory is a human label yet.

## Contents

| File | Purpose |
|---|---|
| `QUEUE_MANIFEST.json` | Frozen queues + hashes. `sealed` = audit content (candidate answers, gold, condition map) — **keep closed during review**. `reviewer_view` = display-safe. |
| `FROZEN.sha256` | SHA-256 of every frozen component + total. |
| `ANNOTATION_GUIDELINE.md` | Frozen researcher-facing protocol (hashed in the manifest). |
| `SCHEMA.md` | Record schemas for all four human-record files. |
| `REVIEWER_SHEET.md` | The only sanctioned display surface. |
| `BASE_22_HUMAN_SIGNED.jsonl` | Empty. Researcher fills + signs. |
| `PAIRED_12_HUMAN_SIGNED.jsonl` | Empty. Researcher fills + signs. |
| `BLIND_REPEAT_5.jsonl` | Empty. Two passes (`pass: 1`, `pass: 2`). |
| `INTERFACE_PILOT_9.jsonl` | Empty. Researcher fills + signs. |
| `INTRA_RATER_RELIABILITY.md` | Methodology + status (NO_DATA until both passes). |
| `ANNOTATION_DISAGREEMENTS.md` | Template; preserves unresolved/ambiguous cases. |
| `RESEARCHER_REFLECTION.md` | Empty structured template — researcher writes it. |

## How to work

1. `python -m experiments.a9_human.run_day1 verify` — confirm hashes match
   before you start.
2. Annotate using the neutral CLI (below), or `REVIEWER_SHEET.md`; never open
   the `sealed` section of the manifest before first-pass labels are frozen.
3. After signing, re-run `verify` (hashes unchanged — human records are NOT
   hashed components; the queues must not change).
4. `python -m experiments.a9_human.run_day1 reliability`
5. `python -m experiments.a9_human.run_day1 vista`

## Annotation CLI (strictly neutral, human-controlled)

The CLI never infers, recommends, or displays candidate labels / model
predictions / scores / prior answers; it never auto-signs; it never changes the
frozen queues or hashes. It only displays frozen questions + permitted
evidence, collects literal human input, validates types/enums/evidence IDs,
saves unsigned drafts (Ctrl+C-safe), shows the completed draft, and requests an
explicit typed signature.

```bash
# Verify frozen hashes before starting.
python -m experiments.a9_human.run_day1 verify

# Status: signed counts, unsigned drafts, blind gate, violations.
python -m experiments.a9_human.run_day1 status

# Annotate (resume skips already-signed cases).
python -m experiments.a9_human.run_day1 annotate base --reviewer-id ELIAN_PRIMARY --resume
python -m experiments.a9_human.run_day1 annotate paired --reviewer-id ELIAN_PRIMARY --resume
python -m experiments.a9_human.run_day1 annotate interface --reviewer-id ELIAN_PRIMARY --resume
python -m experiments.a9_human.run_day1 annotate blind --reviewer-id ELIAN_PRIMARY  # pass 2, gated

# Optional scoping flags.
python -m experiments.a9_human.run_day1 annotate base --reviewer-id ELIAN_PRIMARY --limit 5
python -m experiments.a9_human.run_day1 annotate base --reviewer-id ELIAN_PRIMARY --case-id <case_id>
python -m experiments.a9_human.run_day1 annotate base --reviewer-id ELIAN_PRIMARY --start-at <case_id>

# Review an unsigned draft exactly as stored (no suggestions).
python -m experiments.a9_human.run_day1 review-draft <case_id>

# Sign a saved draft (requires typing SIGN <case_id>).
python -m experiments.a9_human.run_day1 sign <case_id> --reviewer-id ELIAN_PRIMARY

# Amend a signed record (appends a NEW record + audit entry; never overwrites).
python -m experiments.a9_human.run_day1 correct <case_id> --queue base \
    --reviewer-id ELIAN_PRIMARY --reason "correction reason"

# Analysis (after both blind passes).
python -m experiments.a9_human.run_day1 reliability
python -m experiments.a9_human.run_day1 vista
```

The blind repeat refuses to start until all 22 base cases are signed AND the
frozen 4-hour waiting period has elapsed. During pass 2 it hides all pass-1
labels, notes, evidence selections, and confidence.

## Evidence Review Workbench (optional web UI)

The workbench is a local-only web interface for the same annotation flow. It
uses the same authoritative signing/schema/queue logic and never writes signed
JSONL directly. It binds to 127.0.0.1, performs no outbound network calls, and
keeps drafts/sessions in a gitignored SQLite database.

```bash
# Install (optional dependency group).
python -m pip install -e ".[human-workbench]"

# Start the workbench (opens the default browser; resume first unfinished case).
python -m experiments.a9_human.run_day1 serve --reviewer-id ELIAN_PRIMARY

# Isolated smoke test (never touches real JSONL).
python -m experiments.a9_human.run_day1 serve --reviewer-id TEST_REVIEWER \
    --smoke-test --no-browser
```

URL: `http://127.0.0.1:8765`. Optional flags: `--host 127.0.0.1 --port 8765
--no-browser --mode base|paired|interface|blind --case-id <ID> --resume`.

### Researcher workflow (both CLI and workbench are equivalent)

1. annotate and sign 22 base cases;
2. annotate and sign 12 paired cases;
3. complete 9 interface cases;
4. wait at least four hours;
5. complete 5 blind repeats;
6. run `reliability`;
7. run `vista`;
8. personally complete `RESEARCHER_REFLECTION.md`;
9. run the final integrity gates below.

### Final commands

```bash
python -m experiments.a9_human.run_day1 status
python -m experiments.a9_human.run_day1 verify
python -m experiments.a9_human.run_day1 reliability
python -m experiments.a9_human.run_day1 vista
python -m experiments.a0_integrity.run
python -m finvest.release.validate
pytest tests/finvest/
```

See `docs/human_workbench/` for architecture, scientific boundaries, security
model, evidence resolution, human-factors design, test report, and smoke test.

## Rules (summary)

AI never fills, infers, or signs human labels. No inter-rater claims. No
significance claims. No A9 COMPLETE status. Unresolved cases are preserved.
Human records are NOT hashed components; the queues and hashes must never
change.

## How to work (web workbench — ACTIVE protocol v0.2-draft)

The web workbench annotates the ACTIVE draft protocol (v0.2-draft) by
default; its base queue holds the reference-sheet cases (10 candidate sheets
in `v0.2-draft/reference_sheets/`, 9 signable + 1 insufficient case that
needs a negative-evidence certificate).

1. Freeze the active protocol (regenerates QUEUE_MANIFEST.json from the real
   SEC cache; the committed sheets stay under v0.2-draft/reference_sheets/):

       python - <<'PY'
       from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1, verify_frozen
       from finvest.human_study.protocol_config import V0_2_DRAFT
       freeze_day1(seed=FREEZE_SEED, day1_dir=V0_2_DRAFT.dir, protocol=V0_2_DRAFT)
       print(verify_frozen(day1_dir=V0_2_DRAFT.dir))
       PY

2. Start the workbench:

       python -m uvicorn finvest.human_study.web.app:app --port 8000

   (FINVEST_DAY1 defaults to v0.2-draft; override with
   `FINVEST_DAY1=human_review/day1/v0.1` to view the immutable v0.1 artifact.)

3. Open http://127.0.0.1:8000/ — the base queue lists all candidate cases.
   Each case page shows the Self-Contained Human Evidence Package: explicit
   metric definition, human-readable evidence table, independent calculation
   (inputs only; the machine candidate stays sealed until your first-pass
   label is frozen), time & version card, and technical details.

4. Answer the 3 natural questions (Q1 answerable / Q2 answer + calculation /
   Q3 conflicts); the system maps them transparently into the record schema
   (shown before signing). Sign with the typed confirmation `SIGN <case-id>`.

5. Practice mode: /practice/<case-id> shows only the evidence package; the
   reference answer appears only after you submit your own judgement.
