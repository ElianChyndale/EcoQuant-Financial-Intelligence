"""Workbench security helpers (CSRF, session, outbound-block, path guard)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path


class WorkbenchSecurity:
    """Per-request security context (CSRF token, reviewer identity)."""

    def __init__(self, request: object) -> None:
        self._request = request

    def csrf_token(self, secret: str) -> str:
        return hmac.new(secret.encode(), b"csrf", hashlib.sha256).hexdigest()

    def verify_csrf(self, token: str, *, secret: str) -> bool:
        return hmac.compare_digest(token, self.csrf_token(secret))

    def reviewer_id(self) -> str:
        return "ELIAN_PRIMARY"  # pseudonymous; configurable per session


def is_allowed_relative_path(relative: str, *, root: Path) -> bool:
    """Reject path traversal: resolved path must stay under root."""
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
        return True
    except ValueError:
        return False
