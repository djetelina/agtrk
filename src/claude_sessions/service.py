"""Service layer for claude-sessions.

Sits between db.py (raw SQL/connection management) and cli.py (Typer commands).
All functions accept an open sqlite3.Connection — callers are responsible for
obtaining the connection (e.g. via get_db()).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from claude_sessions.models import Note, Session, Status, generate_slug


@dataclass
class SessionWithNotes:
    """A Session together with its associated notes."""

    id: str
    task: str
    repo: Optional[str]
    status: Status
    jira: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    notes: list[Note]


# ---------------------------------------------------------------------------
# register_session
# ---------------------------------------------------------------------------


def register_session(
    conn: sqlite3.Connection,
    task: str,
    repo: Optional[str] = None,
    status: str = "planning",
    jira: Optional[str] = None,
    note: Optional[str] = None,
) -> Session:
    """Create a new session and optionally attach an initial note.

    Args:
        conn: Open database connection.
        task: Human-readable task description (used to derive the slug/id).
        repo: Optional repository name.
        status: Initial status string (default ``"planning"``).
        jira: Optional Jira ticket key.
        note: Optional initial note content.

    Returns:
        The newly created :class:`~claude_sessions.models.Session`.
    """
    rows = conn.execute("SELECT id FROM session").fetchall()
    existing_slugs: set[str] = {row["id"] for row in rows}

    slug = generate_slug(task, existing_slugs)
    now = datetime.now().isoformat()

    conn.execute(
        """
        INSERT INTO session (id, task, repo, status, jira, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, task, repo, status, jira, now, now),
    )

    if note is not None:
        conn.execute(
            "INSERT INTO note (session_id, content, created_at) VALUES (?, ?, ?)",
            (slug, note, now),
        )

    conn.commit()

    return Session(
        id=slug,
        task=task,
        repo=repo,
        status=Status(status),
        jira=jira,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
        completed_at=None,
    )


# ---------------------------------------------------------------------------
# _resolve_session_id
# ---------------------------------------------------------------------------


def _resolve_session_id(conn: sqlite3.Connection, id_or_prefix: str) -> str:
    """Resolve a full ID or unique prefix to a session id.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a prefix string.

    Returns:
        The matching session id.

    Raises:
        ValueError: If no match is found or the prefix is ambiguous.
    """
    # Try exact match first
    exact = conn.execute(
        "SELECT id FROM session WHERE id = ?", (id_or_prefix,)
    ).fetchone()
    if exact is not None:
        return exact["id"]

    # Prefix match
    matches = conn.execute(
        "SELECT id FROM session WHERE id LIKE ?", (f"{id_or_prefix}%",)
    ).fetchall()

    if len(matches) == 0:
        raise ValueError(f"No session found matching '{id_or_prefix}'")

    if len(matches) > 1:
        matched_ids = ", ".join(row["id"] for row in matches)
        raise ValueError(
            f"Ambiguous prefix '{id_or_prefix}' matches: {matched_ids}"
        )

    return matches[0]["id"]


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------


def get_session(conn: sqlite3.Connection, id_or_prefix: str) -> SessionWithNotes:
    """Fetch a session and all its notes.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.

    Returns:
        A :class:`SessionWithNotes` with notes ordered by ``created_at``.

    Raises:
        ValueError: If the id/prefix doesn't match exactly one session.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)

    row = conn.execute(
        "SELECT id, task, repo, status, jira, created_at, updated_at, completed_at "
        "FROM session WHERE id = ?",
        (session_id,),
    ).fetchone()

    note_rows = conn.execute(
        "SELECT id, session_id, content, created_at "
        "FROM note WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    notes = [
        Note(
            id=nr["id"],
            session_id=nr["session_id"],
            content=nr["content"],
            created_at=datetime.fromisoformat(nr["created_at"]),
        )
        for nr in note_rows
    ]

    return SessionWithNotes(
        id=row["id"],
        task=row["task"],
        repo=row["repo"],
        status=Status(row["status"]),
        jira=row["jira"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"])
            if row["completed_at"] is not None
            else None
        ),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# _row_to_session
# ---------------------------------------------------------------------------


def _row_to_session(row: sqlite3.Row) -> Session:
    """Convert a sqlite3.Row from the session table to a Session dataclass."""
    return Session(
        id=row["id"],
        task=row["task"],
        repo=row["repo"],
        status=Status(row["status"]),
        jira=row["jira"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"])
            if row["completed_at"] is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# update_session
# ---------------------------------------------------------------------------


def update_session(
    conn: sqlite3.Connection,
    id_or_prefix: str,
    task: Optional[str] = None,
    repo: Optional[str] = None,
    status: Optional[str] = None,
    jira: Optional[str] = None,
    note: Optional[str] = None,
) -> Session:
    """Update session fields and optionally append a note.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.
        task: New task description (optional).
        repo: New repo value (optional).
        status: New status string (optional).
        jira: New Jira ticket key (optional).
        note: Note content to append to the session timeline (optional).

    Returns:
        The updated :class:`~claude_sessions.models.Session`.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    fields: dict[str, object] = {"updated_at": now}
    if task is not None:
        fields["task"] = task
    if repo is not None:
        fields["repo"] = repo
    if status is not None:
        fields["status"] = status
    if jira is not None:
        fields["jira"] = jira

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    values = list(fields.values()) + [session_id]
    conn.execute(f"UPDATE session SET {set_clause} WHERE id = ?", values)  # noqa: S608

    if note is not None:
        conn.execute(
            "INSERT INTO note (session_id, content, created_at) VALUES (?, ?, ?)",
            (session_id, note, now),
        )

    conn.commit()

    row = conn.execute(
        "SELECT id, task, repo, status, jira, created_at, updated_at, completed_at "
        "FROM session WHERE id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_session(row)


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


def heartbeat(conn: sqlite3.Connection, id_or_prefix: str) -> Session:
    """Bump updated_at without changing any other fields.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.

    Returns:
        The updated :class:`~claude_sessions.models.Session`.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE session SET updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.commit()

    row = conn.execute(
        "SELECT id, task, repo, status, jira, created_at, updated_at, completed_at "
        "FROM session WHERE id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_session(row)


# ---------------------------------------------------------------------------
# complete_session
# ---------------------------------------------------------------------------


def complete_session(conn: sqlite3.Connection, id_or_prefix: str) -> Session:
    """Mark a session as done.

    Sets ``status`` to ``'done'``, ``completed_at`` to now, and bumps
    ``updated_at``.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.

    Returns:
        The updated :class:`~claude_sessions.models.Session`.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE session SET status = 'done', completed_at = ?, updated_at = ? "
        "WHERE id = ?",
        (now, now, session_id),
    )
    conn.commit()

    row = conn.execute(
        "SELECT id, task, repo, status, jira, created_at, updated_at, completed_at "
        "FROM session WHERE id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_session(row)


# ---------------------------------------------------------------------------
# reopen_session
# ---------------------------------------------------------------------------


def reopen_session(
    conn: sqlite3.Connection,
    id_or_prefix: str,
    status: str = "implementing",
) -> Session:
    """Reopen a completed session.

    Clears ``completed_at``, sets ``status`` to *status*, and bumps
    ``updated_at``.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.
        status: Status to transition to (default ``"implementing"``).

    Returns:
        The updated :class:`~claude_sessions.models.Session`.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE session SET status = ?, completed_at = NULL, updated_at = ? "
        "WHERE id = ?",
        (status, now, session_id),
    )
    conn.commit()

    row = conn.execute(
        "SELECT id, task, repo, status, jira, created_at, updated_at, completed_at "
        "FROM session WHERE id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_session(row)


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


def list_sessions(
    conn: sqlite3.Connection,
    include_archived: bool = False,
    archived_only: bool = False,
) -> list[Session]:
    """Return a list of sessions ordered by updated_at descending.

    Args:
        conn: Open database connection.
        include_archived: When True, return all sessions regardless of completion.
        archived_only: When True, return only completed sessions.

    Returns:
        A list of :class:`~claude_sessions.models.Session` objects.
    """
    if archived_only:
        where = "WHERE completed_at IS NOT NULL"
    elif include_archived:
        where = ""
    else:
        where = "WHERE completed_at IS NULL"

    rows = conn.execute(
        f"SELECT id, task, repo, status, jira, created_at, updated_at, completed_at "  # noqa: S608
        f"FROM session {where} ORDER BY updated_at DESC"
    ).fetchall()

    return [_row_to_session(row) for row in rows]


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


def cleanup(conn: sqlite3.Connection, older_than_days: int = 30) -> int:
    """Delete archived sessions older than the given threshold.

    Notes are deleted automatically via CASCADE.

    Args:
        conn: Open database connection.
        older_than_days: Sessions with completed_at older than this many days
            are deleted.

    Returns:
        The number of sessions deleted.
    """
    cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
    cursor = conn.execute(
        "DELETE FROM session WHERE completed_at IS NOT NULL AND completed_at < ?",
        (cutoff,),
    )
    conn.commit()
    return cursor.rowcount
