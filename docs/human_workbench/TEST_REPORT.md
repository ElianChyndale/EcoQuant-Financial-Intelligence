# Workbench Test Report

**Date:** 2026-08-06
**Run:** `pytest tests/finvest/` → **129 passed**, 0 failed

## Coverage by test file

| File | Tests | Proves |
|---|---|---|
| `test_workbench.py` | 18 | neutrality, evidence, security, drafts, signing, human factors |
| `test_workbench_smoke.py` | 1 | isolated smoke: server data, evidence, autosave, no-outbound, signing-blocked |
| `test_annotate_cli.py` | 17 | 12 CLI scientific-boundary proofs + interface/status/paired extras |
| `test_day1_pilot.py` | 27 | freeze/verify/reliability/VISTA gating |
| `test_*` (rest of finvest) | 66 | schemas, splitters, leakage, parsers, selection, verification, M7, M9 |

## Key proofs

- **No candidate labels / model outputs / scores in UI**: `FORBIDDEN_DISPLAY_KEYS`
  projection test + `project_case` allowlist test.
- **No auto-sign**: signing requires typed `SIGN <key>`; wrong confirmation
  raises; draft survives Ctrl+C.
- **Evidence**: all 22 base cases resolve or report an explicit
  `EVIDENCE_RESOLUTION_FAILED` with the missing asset; missing source → explicit
  failure (never fabricated).
- **Neutrality**: mechanical checks contain none of the forbidden decision
  phrases; arithmetic check is descriptive ("The arithmetic result from the
  displayed inputs is ...").
- **Security**: path traversal rejected; annotation app imports no network
  client; static assets contain no external URLs/CDN domains; keyboard
  shortcuts never sign.
- **Drafts**: SQLite autosave survives DB close/reopen; drafts never counted
  as signed; signing idempotently rejects duplicates.

## Observed timings (local, one run)

- Slowest individual test: `test_dense_retrieves` 14.75s (dense model encode).
- `test_smoke_test_passes_isolated` 5.51s (freeze + resolve + sign probe).
- Full finvest suite: 142s (dense-model tests dominate; the workbench itself
  renders sub-second).

## Performance design targets

- first page usable < 3s after server start (static local assets only);
- case navigation < 500 ms after preload (Jinja2 render, no reparse);
- evidence tabs < 300 ms when locally cached;
- autosave < 200 ms (single SQLite upsert).
