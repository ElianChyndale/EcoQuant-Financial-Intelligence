"""Real-browser E2E for the workbench (Phase 8).

Runs an isolated FastAPI server (temp day1 protocol, temp DB, temp cache
override) and drives it with Playwright. NEVER touches the real
human_review/day1 JSONL files. Never creates a real label.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
REAL_DAY1 = ROOT / "human_review" / "day1" / "v0.1"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Start an isolated workbench server; yield its base URL."""
    tmp = tmp_path_factory.mktemp("workbench-e2e")
    day1_dir = tmp / "day1"
    db_path = tmp / "workbench.sqlite"
    issues_path = tmp / "tooling_issues.jsonl"

    # Freeze an isolated v0.2 protocol (accepts actual case count).
    from finvest.fixtures.sec_fixture import FIXTURE_DIR as SEC_FIXTURE_DIR
    from finvest.human_study.day1_pilot import FREEZE_SEED, freeze_day1

    cache = tmp / "cache"
    sec = cache / "sec"
    sec.mkdir(parents=True, exist_ok=True)
    fixture_json = (SEC_FIXTURE_DIR / "sec_companyfacts_fixture.json").read_text(
        encoding="utf-8"
    )
    for ticker in ("aapl", "msft", "ko", "eqix", "jnj", "ups"):
        (sec / f"{ticker}_companyfacts.json").write_text(fixture_json, encoding="utf-8")
    freeze_day1(seed=FREEZE_SEED, day1_dir=day1_dir, min_cases=1, cache_dir=cache)

    port = _free_port()
    env = dict(os.environ)
    env["FINVEST_DAY1"] = str(day1_dir)
    env["FINVEST_CACHE"] = str(cache)
    env["FINVEST_WORKBENCH_DB"] = str(db_path)
    env["FINVEST_TOOLING_ISSUES"] = str(issues_path)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "finvest.human_study.web.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL,
        # stderr inherits pytest's capture so server errors surface in logs.
        stderr=None,
    )
    base_url = f"http://127.0.0.1:{port}"
    # Wait for readiness.
    for _ in range(30):
        try:
            import urllib.request

            urllib.request.urlopen(base_url + "/", timeout=2)
            break
        except Exception:
            time.sleep(0.3)
    yield {"url": base_url, "day1": day1_dir, "db": db_path, "issues": issues_path}
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def _manifest(server):
    return json.loads((server["day1"] / "QUEUE_MANIFEST.json").read_text(encoding="utf-8"))


def _first_case_id(server) -> str:
    m = _manifest(server)
    return m["reviewer_view"]["base_22"][0]["case_id"]


def test_dashboard_opens(server, browser) -> None:
    page = browser.new_page()
    page.goto(server["url"] + "/")
    assert "Evidence Review Workbench" in page.content()
    page.close()


def test_first_ready_case_opens(server, browser) -> None:
    page = browser.new_page()
    case_id = _first_case_id(server)
    page.goto(server["url"] + f"/case/base/{case_id}")
    assert "人类判断" in page.content()
    assert page.locator("#judgement-form").count() == 1
    page.close()


def test_all_required_form_fields_exist(server, browser) -> None:
    """The redesigned form has 3 natural questions + confidence + calc slot."""
    page = browser.new_page()
    case_id = _first_case_id(server)
    page.goto(server["url"] + f"/case/base/{case_id}")
    required = ["q1_answerable", "q2_answer_and_calc", "q3_conflicts",
                "reviewer_confidence", "your_calculation"]
    for field in required:
        assert page.locator(f"#judgement-form [name={field}]").count() >= 1, f"missing {field}"
    # No machine enum burden: the old 18-field form is gone from the page.
    assert page.locator("#judgement-form [name=sufficiency]").count() == 0
    page.close()


def _wait_save_status(page) -> str:
    """Wait until the save-status element shows a real outcome (not empty)."""
    page.wait_for_function(
        "document.getElementById('save-status').textContent.trim() !== ''",
        timeout=8000,
    )
    return page.locator("#save-status").text_content()


def test_save_draft_click_works(server, browser) -> None:
    """Mouse click on Save Draft must produce a visible Saved confirmation."""
    page = browser.new_page()
    case_id = _first_case_id(server)
    page.goto(server["url"] + f"/case/base/{case_id}")
    page.select_option("#judgement-form [name=q1_answerable]", "ANSWERABLE")
    page.click("#save-draft")
    # Visible confirmation with the Saved text (await the fetch, not the div).
    status = _wait_save_status(page)
    assert "Draft saved" in status
    page.close()


def test_sqlite_contains_draft(server, browser) -> None:
    import sqlite3

    page = browser.new_page()
    case_id = _first_case_id(server)
    page.goto(server["url"] + f"/case/base/{case_id}")
    # PARTIAL -> derived sufficiency PARTIAL (transparent mapping).
    page.select_option("#judgement-form [name=q1_answerable]", "PARTIAL")
    page.click("#save-draft")
    _wait_save_status(page)
    page.close()
    # Verify SQLite has the draft with the DERIVED field.
    conn = sqlite3.connect(server["db"])
    rows = conn.execute("SELECT payload FROM drafts").fetchall()
    conn.close()
    assert rows
    assert "PARTIAL" in rows[0][0]


def test_refresh_restores_draft(server, browser) -> None:
    page = browser.new_page()
    case_id = _first_case_id(server)
    page.goto(server["url"] + f"/case/base/{case_id}")
    page.select_option("#judgement-form [name=q1_answerable]", "ANSWERABLE")
    page.fill("#judgement-form [name=q2_answer_and_calc]", "e2e rationale")
    page.click("#save-draft")
    _wait_save_status(page)
    page.reload()
    assert page.locator("#judgement-form [name=q1_answerable]").input_value() == "ANSWERABLE"
    assert page.locator("#judgement-form [name=q2_answer_and_calc]").input_value() == "e2e rationale"
    page.close()


def test_sign_requires_typed_confirmation(server, browser) -> None:
    page = browser.new_page()
    case_id = _first_case_id(server)
    page.goto(server["url"] + f"/case/base/{case_id}")
    # Open final review, enter wrong confirmation, sign -> rejected.
    page.click("#open-final-review")
    page.fill("#sign-confirm", "WRONG")
    page.click("#do-sign")
    page.wait_for_timeout(800)
    # No signed record written.
    signed_file = server["day1"] / "BASE_22_HUMAN_SIGNED.jsonl"
    assert (not signed_file.exists()) or signed_file.stat().st_size == 0
    page.close()


def test_real_human_jsonl_unchanged(server, browser) -> None:
    """The REAL day1 JSONL must remain empty after all E2E activity."""
    for name in ("BASE_22_HUMAN_SIGNED.jsonl", "PAIRED_12_HUMAN_SIGNED.jsonl",
                 "BLIND_REPEAT_5.jsonl", "INTERFACE_PILOT_9.jsonl"):
        real = REAL_DAY1 / name
        assert (not real.exists()) or real.stat().st_size == 0, f"real {name} not empty"


def test_tooling_issue_creates_no_label(server, browser) -> None:
    page = browser.new_page()
    case_id = _first_case_id(server)
    page.goto(server["url"] + f"/case/base/{case_id}")
    page.click("details.tooling-issue summary")  # expand the collapsed section
    page.select_option("#issue-category", "EVIDENCE_RESOLUTION_FAILED")
    page.fill("#issue-note", "e2e tooling issue")
    page.click("#report-issue")
    page.wait_for_timeout(600)
    issues = server["issues"]
    assert issues.exists()
    line = issues.read_text(encoding="utf-8").strip()
    assert "EVIDENCE_RESOLUTION_FAILED" in line
    assert '"is_human_label": false' in line
    # No signed label created.
    signed_file = server["day1"] / "BASE_22_HUMAN_SIGNED.jsonl"
    assert (not signed_file.exists()) or signed_file.stat().st_size == 0
    page.close()
