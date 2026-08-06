"""FinVEST Evidence Review Workbench — local-only FastAPI app.

Architecture:
- FastAPI + Jinja2 + HTMX (vendored local static asset; no CDN).
- SQLite (gitignored) for unsigned drafts / sessions / timers / interaction
  audit. Signed JSONL stays authoritative and is only written through the
  existing signing service.
- Binds to 127.0.0.1 only. No outbound network calls. No LLM.

Scientific boundary: the app NEVER renders candidate labels, model outputs,
scores, gold answers, prior annotations, or label recommendations. Mechanical
checks are descriptive facts only. Evidence is the ORIGINAL local source; if it
cannot be resolved, the UI shows EVIDENCE_RESOLUTION_FAILED.
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from finvest.human_study.annotate_cli import load_manifest
from finvest.human_study.web.security import WorkbenchSecurity
from finvest.human_study.web.services.draft_service import DraftService
from finvest.human_study.web.services.evidence_service import resolve_evidence_set
from finvest.human_study.web.services.mechanical_checks import run_neutral_checks
from finvest.human_study.web.services.preflight import preflight_case, preflight_queues
from finvest.human_study.web.services.queue_service import (
    queue_keys,
    queue_views,
    signed_keys,
)
from finvest.human_study.web.services.signing_adapter import (
    append_signed,
    is_signed,
    record_problems_for,
)
from finvest.human_study.web.services.tooling_issue import report_tooling_issue

ROOT = Path(__file__).resolve().parents[3]
TOOLING_ISSUE_PATH = ROOT / "research" / "cache" / "workbench" / "tooling_issues.jsonl"
DAY1 = ROOT / "human_review" / "day1"
CACHE = ROOT / "research" / "cache"
DB_PATH = ROOT / "research" / "cache" / "workbench" / "workbench.sqlite"

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = DraftService(DB_PATH)
    app.state.secret = secrets.token_hex(16)
    yield
    app.state.db.close()


app = FastAPI(title="FinVEST Evidence Review Workbench", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def _manifest() -> dict:
    return load_manifest(DAY1)


def _view_for(queue: str, key: str) -> dict | None:
    for view in queue_views(DAY1, queue, _manifest()):
        if view.get("case_id") == key or view.get("review_token") == key or view.get("temp_id") == key:
            return view
    return None


def _security(request: Request) -> WorkbenchSecurity:
    return WorkbenchSecurity(request)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, reviewer: str = "ELIAN_PRIMARY"):
    manifest = _manifest()
    rows = []
    for queue in ("base", "paired", "interface", "blind"):
        keys = queue_keys(DAY1, queue, manifest)
        signed = len(signed_keys(DAY1, queue))
        total = len(keys)
        rows.append({
            "queue": queue,
            "signed": signed,
            "total": total,
            "complete": signed >= total,
            "first_key": keys[0] if keys else None,
        })
    # Preflight counts for the base queue (READY / TOOLING_BLOCKED / INVALID).
    preflight = preflight_queues(manifest, cache=CACHE)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "reviewer": reviewer, "rows": rows,
        "preflight": preflight,
    })


@app.get("/favicon.ico")
def favicon():
    return RedirectResponse("/static/favicon.svg")


@app.get("/dashboard/{queue}", response_class=HTMLResponse)
def queue_dashboard(request: Request, queue: str):
    """Redirect /dashboard/{queue} to the first unfinished case."""
    manifest = _manifest()
    keys = queue_keys(DAY1, queue, manifest)
    if not keys:
        return HTMLResponse("empty queue", status_code=404)
    # First unfinished case (resume logic).
    signed = set(signed_keys(DAY1, queue))
    for key in keys:
        if key not in signed:
            return RedirectResponse(f"/case/{queue}/{key}")
    return RedirectResponse(f"/case/{queue}/{keys[-1]}")


@app.get("/case/{queue}/{key}", response_class=HTMLResponse)
def case_view(request: Request, queue: str, key: str, reviewer: str = "ELIAN_PRIMARY"):
    manifest = _manifest()
    view = _view_for(queue, key)
    if view is None:
        return HTMLResponse("case not found", status_code=404)
    db: DraftService = request.app.state.db
    draft = db.load_draft(reviewer, queue, key)
    # Resolve ORIGINAL evidence from the local cache.
    evidence_items = view.get("evidence", [])
    resolved = resolve_evidence_set(evidence_items, CACHE)
    checks = run_neutral_checks(
        evidence_items,
        source_cutoff=view.get("source_cutoff"),
        case_issuer=view.get("issuer"),
    )
    signed_state = is_signed(DAY1, queue, key)
    # Preflight: only READY cases are signable.
    preflight = preflight_case(view, queue=queue, cache=CACHE) if queue == "base" else None
    return templates.TemplateResponse("case_base.html", {
        "request": request, "queue": queue, "key": key, "view": view,
        "resolved_evidence": resolved, "checks": checks,
        "draft": draft, "signed": signed_state, "reviewer": reviewer,
        "preflight": preflight,
    })


@app.post("/draft/{queue}/{key}")
def save_draft(
    request: Request,
    queue: str,
    key: str,
    reviewer: str = Form(...),
    payload: str = Form(...),
):
    db: DraftService = request.app.state.db
    import json

    db.save_draft(reviewer, queue, key, json.loads(payload))
    db.record_interaction(reviewer, key, "autosave")
    return JSONResponse({"ok": True})


@app.post("/tooling-issue/{queue}/{key}")
def tooling_issue(
    request: Request,
    queue: str,
    key: str,
    reviewer: str = Form(...),
    evidence_id: str = Form(None),
    category: str = Form(...),
    note: str = Form(""),
):
    """Report a tooling issue (never a human label)."""
    db: DraftService = request.app.state.db
    request_id = request.headers.get("x-request-id", "web")
    try:
        report_tooling_issue(
            issue_path=TOOLING_ISSUE_PATH,
            case_id=key,
            queue=queue,
            evidence_id=evidence_id or None,
            category=category,
            note=note,
            reviewer_id=reviewer,
            commit="fix/day1-v0.2-scientific-e2e",
            request_id=request_id,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    db.record_interaction(reviewer, key, "tooling_issue", category)
    return JSONResponse({"ok": True})


@app.post("/sign/{queue}/{key}")
def sign(
    request: Request,
    queue: str,
    key: str,
    reviewer: str = Form(...),
    payload: str = Form(...),
    confirmation: str = Form(...),
):
    import json

    manifest = _manifest()
    db: DraftService = request.app.state.db
    record = json.loads(payload)
    # Preflight gate: never sign a TOOLING_BLOCKED or INVALID case.
    if queue == "base":
        view = _view_for(queue, key)
        if view is not None:
            preflight = preflight_case(view, queue=queue, cache=CACHE)
            if preflight.status != "READY_FOR_ANNOTATION":
                return JSONResponse(
                    {"ok": False, "error": f"case not signable: {preflight.status} ({preflight.reason})"},
                    status_code=400,
                )
    try:
        signed = append_signed(
            DAY1, queue, key, record, reviewer, confirmation, manifest,
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    db.delete_draft(reviewer, queue, key)
    db.record_interaction(reviewer, key, "signed")
    return JSONResponse({"ok": True, "key": signed.get("case_id") or signed.get("review_token") or signed.get("temp_id")})
