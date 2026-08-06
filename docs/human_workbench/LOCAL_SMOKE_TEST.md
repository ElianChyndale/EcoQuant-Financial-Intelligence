# Workbench Local Smoke Test

**Date:** 2026-08-06
**Command:** `python -m experiments.a9_human.run_day1 serve --reviewer-id TEST_REVIEWER --smoke-test --no-browser`

## What it validates (isolated)

The smoke test runs entirely in a temp directory — it freezes a temp day1 copy,
uses a temp SQLite DB, and NEVER writes to the real `human_review/day1/*.jsonl`
or creates a real label.

| Check | Result |
|---|---|
| Server data: 4 frozen queues present | PASS |
| One base case renders + evidence resolves from local cache | PASS (2 evidence items) |
| Draft autosave to isolated SQLite | PASS |
| Signing requires explicit typed `SIGN <key>` confirmation | PASS (wrong confirmation rejected) |
| No signed JSONL written in the isolated run | PASS |
| No outbound network imports in the annotation app | PASS |

## Alternative direct invocation

```bash
python -m finvest.human_study.web.smoke_test
```

Runs the same isolated smoke test and exits 0 iff all pass.

## Note on the real serve command

`serve --smoke-test` patches the workbench DB path to
`research/cache/workbench/smoke_test.sqlite` (gitignored) and skips browser
launch. The real annotation flow (`serve` without `--smoke-test`) uses the
normal workbench DB and does NOT touch signed JSONL except through the existing
signing service.
