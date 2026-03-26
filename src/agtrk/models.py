"""Data models for agtrk."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Status(StrEnum):
    todo = "todo"
    planning = "planning"
    implementing = "implementing"
    waiting = "waiting"
    done = "done"


class Kind(StrEnum):
    architecture = "architecture"
    decision = "decision"
    convention = "convention"
    exploration = "exploration"

    @property
    def description(self) -> str:
        return _KIND_DESCRIPTIONS[self]


_KIND_DESCRIPTIONS: dict[Kind, str] = {
    Kind.architecture: "structural facts (where things live, how components connect)",
    Kind.decision: "why something was chosen over alternatives",
    Kind.convention: "patterns, coding standards, tooling choices",
    Kind.exploration: "other discovered facts worth preserving",
}


class Feature(StrEnum):
    knowledge = "knowledge"


@dataclass
class Session:
    id: str
    task: str
    repo: str | None
    status: Status
    issue: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    summary: str | None = None


@dataclass
class Note:
    id: int
    session_id: str
    content: str
    created_at: datetime
    repo: str | None = None
    branch: str | None = None
    cwd: str | None = None
    worktree: bool | None = None


@dataclass
class Knowledge:
    id: int
    repo: str
    kind: Kind
    title: str
    content: str
    created_at: datetime
    updated_at: datetime


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _random_suffix(length: int = 3) -> str:
    """Generate a short random alphanumeric suffix."""
    import secrets
    import string

    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_slug(
    task: str,
    existing_slugs: set[str] | None = None,
    slug_id: str | None = None,
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
