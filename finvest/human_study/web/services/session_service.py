"""Workbench session + security primitives.

- local session tokens (pseudonymous reviewer ID, never the OS username),
- CSRF token for state-changing requests,
- path-traversal guard (paths restricted to approved roots),
- loopback-only binding helper.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path

ALLOWED_ROOTS = ("human_review", "research/cache/sec")


def make_session_token(reviewer_id: str, *, secret: str) -> str:
    """Deterministic-but-unforgeable session token from a pseudonymous reviewer id."""
    nonce = secrets.token_hex(8)
    digest = hmac.new(secret.encode(), f"{reviewer_id}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return f"{reviewer_id}:{nonce}:{digest}"


def verify_session_token(token: str, *, secret: str) -> str | None:
    """Return the reviewer_id if the token is valid, else None."""
    try:
        reviewer_id, nonce, digest = token.split(":", 2)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), f"{reviewer_id}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return reviewer_id if hmac.compare_digest(expected, digest) else None


def make_csrf_token(secret: str) -> str:
    return hmac.new(secret.encode(), b"csrf", hashlib.sha256).hexdigest()


def verify_csrf(token: str, *, secret: str) -> bool:
    return hmac.compare_digest(token, make_csrf_token(secret))


def is_allowed_relative_path(relative: str, *, root: Path) -> bool:
    """Reject path traversal: the resolved path must stay under root."""
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
        return True
    except ValueError:
        return False
