# FinVEST Evidence Review Workbench — Architecture

**Date:** 2026-08-06
**Status:** ENGINEERING_COMPLETE (local-only; zero human labels)

## Overview

A minimal local web application for efficient human annotation of the day-1
pilot. It maximizes time on scientific judgement and minimizes mechanical
effort (searching filings, copying IDs, formatting JSON).

## Stack

- **FastAPI** (local server, binds to 127.0.0.1 only)
- **Jinja2** (server-side templates; no client framework)
- **HTMX-style local JS** (vendored static asset; no CDN)
- **SQLite** (gitignored) for unsigned drafts, sessions, timers, interaction
  audit
- **Existing signed JSONL** as authoritative final human-label records

No React/Vue/Node pipeline, no cloud database, no external analytics, no
outbound network, no external LLM.

## Module layout

```
finvest/human_study/web/
  app.py                 FastAPI app (routes, lifecycle)
  security.py            CSRF, session, path-traversal guard
  models.py              view projections
  services/
    queue_service.py     frozen queue views (CLI-authoritative)
    evidence_service.py  ORIGINAL evidence resolution from local SEC cache
    mechanical_checks.py neutral descriptive checks (never decisions)
    draft_service.py     SQLite autosave/session/timer/interaction
    signing_adapter.py   thin adapter over the authoritative CLI signing
    session_service.py   session tokens + CSRF helpers
  templates/             layout/dashboard/case_base + tab panels
  static/                app.css, app.js (local only)
```

## Key architectural rule

**One source of truth for annotation logic.** The web UI never reimplements
queue parsing, schema validation, record serialization, signing, corrections,
blind-repeat access, or hash verification. It calls the same functions the CLI
calls (`annotate_cli`), wrapped by thin adapters. The only writer of signed
JSONL is the existing signing path.

## Data flow

```
FastAPI route
 -> load_manifest (frozen)
 -> queue_service (frozen views)
 -> evidence_service (resolve ORIGINAL text/table/XBRL from local cache)
 -> mechanical_checks (descriptive facts)
 -> template render (question | evidence tabs | judgement form)
 -> draft autosave (SQLite)
 -> explicit SIGN <key> -> signing_adapter -> append_signed JSONL
```

## Serve command

```bash
python -m experiments.a9_human.run_day1 serve --reviewer-id ELIAN_PRIMARY
```

Optional: `--host 127.0.0.1 --port 8765 --no-browser --mode base|paired|interface|blind
--case-id <ID> --resume --smoke-test`
