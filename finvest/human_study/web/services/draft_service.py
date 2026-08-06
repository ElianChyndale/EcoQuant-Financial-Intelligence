"""SQLite draft/session service (gitignored; never committed).

Stores unsigned drafts, session state, timer checkpoints, and interaction
audit. The AUTHORITATIVE final record is the signed JSONL written by the
existing signing service; this DB is only for interruption-safe work in
progress. Never converts a draft into a label.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
  reviewer_id TEXT NOT NULL,
  queue TEXT NOT NULL,
  key TEXT NOT NULL,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (reviewer_id, queue, key)
);
CREATE TABLE IF NOT EXISTS sessions (
  reviewer_id TEXT PRIMARY KEY,
  queue TEXT,
  current_key TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timer_checkpoints (
  reviewer_id TEXT NOT NULL,
  key TEXT NOT NULL,
  active_seconds REAL NOT NULL,
  last_tick TEXT NOT NULL,
  PRIMARY KEY (reviewer_id, key)
);
CREATE TABLE IF NOT EXISTS interaction_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reviewer_id TEXT NOT NULL,
  key TEXT,
  event TEXT NOT NULL,
  detail TEXT,
  ts TEXT NOT NULL
);
"""


class DraftService:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @contextmanager
    def _tx(self):
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def save_draft(self, reviewer_id: str, queue: str, key: str, payload: dict) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO drafts(reviewer_id, queue, key, payload, updated_at) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(reviewer_id, queue, key) DO UPDATE SET payload=excluded.payload, "
                "updated_at=excluded.updated_at",
                (reviewer_id, queue, key, json.dumps(payload, default=str), now),
            )

    def load_draft(self, reviewer_id: str, queue: str, key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT payload FROM drafts WHERE reviewer_id=? AND queue=? AND key=?",
            (reviewer_id, queue, key),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def delete_draft(self, reviewer_id: str, queue: str, key: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM drafts WHERE reviewer_id=? AND queue=? AND key=?",
                (reviewer_id, queue, key),
            )

    def draft_keys(self, reviewer_id: str, queue: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT key FROM drafts WHERE reviewer_id=? AND queue=?",
            (reviewer_id, queue),
        ).fetchall()
        return [r[0] for r in rows]

    def set_session(self, reviewer_id: str, queue: str, current_key: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO sessions(reviewer_id, queue, current_key, updated_at) "
                "VALUES(?,?,?,?) ON CONFLICT(reviewer_id) DO UPDATE SET queue=excluded.queue, "
                "current_key=excluded.current_key, updated_at=excluded.updated_at",
                (reviewer_id, queue, current_key, now),
            )

    def get_session(self, reviewer_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT queue, current_key FROM sessions WHERE reviewer_id=?", (reviewer_id,)
        ).fetchone()
        return {"queue": row[0], "current_key": row[1]} if row else None

    def record_interaction(self, reviewer_id: str, key: str | None, event: str, detail: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO interaction_audit(reviewer_id, key, event, detail, ts) VALUES(?,?,?,?,?)",
                (reviewer_id, key, event, detail, now),
            )

    def interactions(self, reviewer_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT key, event, detail, ts FROM interaction_audit WHERE reviewer_id=? "
            "ORDER BY id", (reviewer_id,),
        ).fetchall()
        return [{"key": r[0], "event": r[1], "detail": r[2], "ts": r[3]} for r in rows]

    def close(self) -> None:
        self._conn.close()
