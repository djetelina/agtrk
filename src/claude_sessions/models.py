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


_MAX_SLUG_LEN = 20
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def generate_slug(task: str, existing_slugs: Optional[set[str]] = None) -> str:
    """Generate a URL-safe slug from a task description.

    Args:
        task: Human-readable task description.
        existing_slugs: Set of already-taken slugs. When provided, a numeric
            suffix is appended to avoid collisions.

    Returns:
        A lowercase, hyphen-separated slug of at most 40 characters.
    """
    lowered = task.lower()
    slugified = _NON_ALNUM.sub("-", lowered)
    slugified = slugified.strip("-")
    slugified = slugified[:_MAX_SLUG_LEN].rstrip("-")

    if existing_slugs is None or slugified not in existing_slugs:
        return slugified

    counter = 2
    while True:
        candidate = f"{slugified}-{counter}"
        if candidate not in existing_slugs:
            return candidate
        counter += 1
