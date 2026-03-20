"""Data models for claude-sessions."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional


class Status(StrEnum):
    todo = "todo"
    planning = "planning"
    implementing = "implementing"
    waiting = "waiting"
    done = "done"


@dataclass
class Session:
    id: str
    task: str
    repo: Optional[str]
    status: Status
    issue: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    summary: Optional[str] = None


@dataclass
class Note:
    id: int
    session_id: str
    content: str
    created_at: datetime
    repo: Optional[str] = None
    branch: Optional[str] = None
    cwd: Optional[str] = None
    worktree: Optional[bool] = None


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _random_suffix(length: int = 3) -> str:
    """Generate a short random alphanumeric suffix."""
    import secrets
    import string
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_slug(
    task: str,
    existing_slugs: Optional[set[str]] = None,
    slug_id: Optional[str] = None,
) -> str:
    """Generate a URL-safe session ID.

    If *slug_id* is provided, sanitize it and append a random suffix.
    Otherwise, fall back to deriving a slug from *task*.

    Args:
        task: Human-readable task description (fallback source).
        existing_slugs: Set of already-taken slugs.
        slug_id: Explicit short ID chosen by the caller.

    Returns:
        A unique, lowercase, hyphen-separated slug.
    """
    source = slug_id if slug_id else task
    lowered = source.lower()
    slugified = _NON_ALNUM.sub("-", lowered)
    slugified = slugified.strip("-")

    candidate = f"{slugified}-{_random_suffix()}"
    if existing_slugs is None:
        return candidate

    while candidate in existing_slugs:
        candidate = f"{slugified}-{_random_suffix()}"
    return candidate
