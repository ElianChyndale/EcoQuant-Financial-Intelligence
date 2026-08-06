# Workbench Security Model

**Date:** 2026-08-06

## Mandatory guarantees

- **Loopback only**: binds to 127.0.0.1; refuses non-loopback hosts unless the
  explicit `--allow-unsafe-host` development flag is given.
- **No telemetry, no external scripts, no CDNs, no remote fonts, no outbound
  HTTP, no remote APIs, no external LLM, no cloud database.**
- **Pseudonymous reviewer ID**: never the OS username, personal name, email,
  IP, or browser fingerprint in public output.
- **Raw SEC cache + SQLite draft DB are gitignored.**
- **Signed JSONL stays under existing governance** (the CLI signing service).

## Path traversal

`is_allowed_relative_path` resolves candidate paths and rejects any that escape
the approved root. Arbitrary local-file access is denied.

## File rendering

Filing HTML is escaped/sanitized before rendering. Active scripts from filings
are never executed. Static assets are local-only.

## CSRF

State-changing requests (draft save, sign) require a CSRF token. Session tokens
are HMAC-signed and local.

## Outbound-block test

`test_workbench.py::test_outbound_block_test_exists` asserts the annotation
app source imports no network client (`requests`, `urllib.request`, `httpx`,
`socket`). The smoke test independently confirms the same.

## Concurrency

SQLite WAL + atomic transactions; drafts keyed by `(reviewer_id, queue, key)`.
No two sessions edit the same reviewer/case concurrently by design (per-case
lock).
