"""Service layer for agtrk.

Sits between db.py (raw SQL/connection management) and cli.py (Typer commands).
All functions accept an open sqlite3.Connection — callers are responsible for
obtaining the connection (e.g. via get_db()).
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from agtrk.git import detect_branch, detect_cwd, detect_repo, detect_worktree
from agtrk.models import Feature, Kind, Knowledge, Note, Session, Status, generate_slug

_SESSION_COLUMNS = "id, task, repo, status, issue, created_at, updated_at, completed_at, summary"


@dataclass
class SessionWithNotes:
    """A Session together with its associated notes."""

    session: Session
    notes: list[Note]

    # Delegate attribute access to the inner session for backwards compat
    def __getattr__(self, name: str) -> object:
        return getattr(self.session, name)


def _validate_enum(value: str, enum_cls: type[StrEnum]) -> StrEnum:
    """Validate a string against a StrEnum and return the member."""
    try:
        return enum_cls(value)
    except ValueError:
        label = enum_cls.__name__.lower()
        valid = ", ".join(m.value for m in enum_cls)
        raise ValueError(f"Invalid {label} '{value}'. Must be one of: {valid}") from None


def _like_pattern(term: str) -> str:
    """Escape SQL LIKE special chars and wrap in %...%. Use with ESCAPE '\\\\'."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_session(conn: sqlite3.Connection, session_id: str) -> Session:
    """Fetch a single session row and convert to a Session dataclass."""
    row = conn.execute(
        f"SELECT {_SESSION_COLUMNS} FROM session WHERE id = ?",
        (session_id,),
    ).fetchone()
    return _row_to_session(row)


def _row_to_session(row: sqlite3.Row) -> Session:
    """Convert a sqlite3.Row from the session table to a Session dataclass."""
    return Session(
        id=row["id"],
        task=row["task"],
        repo=row["repo"],
        status=Status(row["status"]),
        issue=row["issue"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        completed_at=(datetime.fromisoformat(row["completed_at"]) if row["completed_at"] is not None else None),
        summary=row["summary"],
    )


def _row_to_note(row: sqlite3.Row) -> Note:
    """Convert a sqlite3.Row from the note table to a Note dataclass."""
    worktree_val = row["worktree"]
    return Note(
        id=row["id"],
        session_id=row["session_id"],
        content=row["content"],
        created_at=datetime.fromisoformat(row["created_at"]),
        repo=row["repo"],
        branch=row["branch"],
        cwd=row["cwd"],
        worktree=bool(worktree_val) if worktree_val is not None else None,
    )


def _create_note(
    conn: sqlite3.Connection,
    session_id: str,
    content: str,
    timestamp: str,
    repo: str | None = None,
    branch: str | None = None,
) -> None:
    """Create a note with auto-detected git context.

    repo and branch are overrides — if None, auto-detection fills them.
    cwd and worktree are always auto-detected.
    """
    note_repo = repo if repo is not None else detect_repo()
    note_branch = branch if branch is not None else detect_branch()
    note_cwd = detect_cwd()
    note_worktree = detect_worktree()
    worktree_int = int(note_worktree) if note_worktree is not None else None

    conn.execute(
        "INSERT INTO note (session_id, content, created_at, repo, branch, cwd, worktree) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, content, timestamp, note_repo, note_branch, note_cwd, worktree_int),
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
    matches = conn.execute("SELECT id FROM session WHERE id LIKE ?", (f"{id_or_prefix}%",)).fetchall()

    if len(matches) == 0:
        raise ValueError(f"No session found matching '{id_or_prefix}'")

    if len(matches) > 1:
        matched_ids = ", ".join(row["id"] for row in matches)
        raise ValueError(f"Ambiguous prefix '{id_or_prefix}' matches: {matched_ids}")

    return matches[0]["id"]


# ---------------------------------------------------------------------------
# register_session
# ---------------------------------------------------------------------------


def register_session(
    conn: sqlite3.Connection,
    task: str,
    slug_id: str | None = None,
    repo: str | None = None,
    status: str = "planning",
    issue: str | None = None,
    note: str | None = None,
) -> Session:
    """Create a new session and optionally attach an initial note.

    Args:
        conn: Open database connection.
        task: Human-readable task description (used to derive the slug/id).
        slug_id: Optional explicit short ID slug.
        repo: Optional repository name.
        status: Initial status string (default ``"planning"``).
        issue: Optional issue/ticket key.
        note: Optional initial note content.

    Returns:
        The newly created :class:`~agtrk.models.Session`.
    """
    _validate_enum(status, Status)

    rows = conn.execute("SELECT id FROM session").fetchall()
    existing_slugs: set[str] = {row["id"] for row in rows}

    slug = generate_slug(task, existing_slugs, slug_id=slug_id)
    now = datetime.now().isoformat()

    conn.execute(
        """
        INSERT INTO session (id, task, repo, status, issue, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, task, repo, status, issue, now, now),
    )

    if note is not None:
        _create_note(conn, slug, note, now, repo=repo)

    conn.commit()

    return Session(
        id=slug,
        task=task,
        repo=repo,
        status=Status(status),
        issue=issue,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
        completed_at=None,
    )


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
    session = _fetch_session(conn, session_id)

    note_rows = conn.execute(
        "SELECT id, session_id, content, created_at, repo, branch, cwd, worktree FROM note WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    return SessionWithNotes(
        session=session,
        notes=[_row_to_note(nr) for nr in note_rows],
    )


# ---------------------------------------------------------------------------
# update_session
# ---------------------------------------------------------------------------


def update_session(
    conn: sqlite3.Connection,
    id_or_prefix: str,
    task: str | None = None,
    repo: str | None = None,
    status: str | None = None,
    issue: str | None = None,
    note: str | None = None,
    branch: str | None = None,
) -> Session:
    """Update session fields and optionally append a note.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.
        task: New task description (optional).
        repo: New repo value (optional).
        status: New status string (optional).
        issue: New issue/ticket key (optional).
        note: Note content to append to the session timeline (optional).

    Returns:
        The updated :class:`~agtrk.models.Session`.
    """
    if status is not None:
        _validate_enum(status, Status)

    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    fields: dict[str, object] = {"updated_at": now}
    if task is not None:
        fields["task"] = task
    if repo is not None:
        fields["repo"] = repo
    if status is not None:
        fields["status"] = status
    if issue is not None:
        fields["issue"] = issue

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    values = [*fields.values(), session_id]
    conn.execute(f"UPDATE session SET {set_clause} WHERE id = ?", values)

    if note is not None:
        _create_note(conn, session_id, note, now, branch=branch)

    conn.commit()
    return _fetch_session(conn, session_id)


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


def heartbeat(conn: sqlite3.Connection, id_or_prefix: str) -> Session:
    """Bump updated_at without changing any other fields.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.

    Returns:
        The updated :class:`~agtrk.models.Session`.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE session SET updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.commit()
    return _fetch_session(conn, session_id)


# ---------------------------------------------------------------------------
# complete_session
# ---------------------------------------------------------------------------


def complete_session(
    conn: sqlite3.Connection,
    id_or_prefix: str,
    summary: str | None = None,
) -> Session:
    """Mark a session as done.

    Sets ``status`` to ``'done'``, ``completed_at`` to now, and bumps
    ``updated_at``. Optionally stores a summary.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.
        summary: Optional summary of what was accomplished.

    Returns:
        The updated :class:`~agtrk.models.Session`.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE session SET status = 'done', completed_at = ?, updated_at = ?, summary = ? WHERE id = ?",
        (now, now, summary, session_id),
    )
    conn.commit()
    return _fetch_session(conn, session_id)


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
        The updated :class:`~agtrk.models.Session`.
    """
    _validate_enum(status, Status)

    session_id = _resolve_session_id(conn, id_or_prefix)
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE session SET status = ?, completed_at = NULL, updated_at = ? WHERE id = ?",
        (status, now, session_id),
    )
    conn.commit()
    return _fetch_session(conn, session_id)


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
        A list of :class:`~agtrk.models.Session` objects.
    """
    if archived_only:
        where = "WHERE completed_at IS NOT NULL"
    elif include_archived:
        where = ""
    else:
        where = "WHERE completed_at IS NULL"

    rows = conn.execute(f"SELECT {_SESSION_COLUMNS} FROM session {where} ORDER BY updated_at DESC").fetchall()

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


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------


def search_sessions(
    conn: sqlite3.Connection,
    query: str,
    include_archived: bool = False,
) -> list[SessionWithNotes]:
    """Search sessions by task/note content.

    Returns sessions where the query matches the task description or any note
    content (case-insensitive LIKE). Each returned SessionWithNotes contains
    only the matching notes.

    Args:
        conn: Open database connection.
        query: Search term (matched with SQL LIKE %query%).
        include_archived: When True, also search completed sessions.

    Returns:
        A list of :class:`SessionWithNotes`, each with only matching notes.
    """
    like_pattern = _like_pattern(query)

    # Find session IDs where task or any note matches
    archive_filter = "" if include_archived else "AND s.completed_at IS NULL"
    id_rows = conn.execute(
        "SELECT DISTINCT s.id "
        "FROM session s "
        "LEFT JOIN note n ON n.session_id = s.id "
        "WHERE (s.task LIKE ? ESCAPE '\\' COLLATE NOCASE OR n.content LIKE ? ESCAPE '\\' COLLATE NOCASE) "
        f"{archive_filter} ",
        (like_pattern, like_pattern),
    ).fetchall()

    # Fetch full session data for each match
    matched_ids = [r["id"] for r in id_rows]
    rows = [_fetch_session(conn, sid) for sid in matched_ids]

    results = []
    for session in sorted(rows, key=lambda s: s.updated_at, reverse=True):
        # Fetch only matching notes for this session
        note_rows = conn.execute(
            "SELECT id, session_id, content, created_at, repo, branch, cwd, worktree "
            "FROM note WHERE session_id = ? AND content LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "ORDER BY created_at ASC",
            (session.id, like_pattern),
        ).fetchall()
        results.append(
            SessionWithNotes(
                session=session,
                notes=[_row_to_note(nr) for nr in note_rows],
            )
        )

    return results


def _row_to_knowledge(row: sqlite3.Row) -> Knowledge:
    """Convert a sqlite3.Row from the knowledge table to a Knowledge dataclass."""
    return Knowledge(
        id=row["id"],
        repo=row["repo"],
        kind=Kind(row["kind"]),
        title=row["title"],
        content=row["content"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


_KNOWLEDGE_COLUMNS = "id, repo, kind, title, content, created_at, updated_at"


# ---------------------------------------------------------------------------
# learn
# ---------------------------------------------------------------------------


def learn(
    conn: sqlite3.Connection,
    repo: str,
    kind: str,
    title: str,
    content: str,
) -> Knowledge:
    """Store a project knowledge entry.

    Args:
        conn: Open database connection.
        repo: Repository identifier.
        kind: Knowledge category (architecture, decision, convention, exploration).
        title: Short searchable summary.
        content: The knowledge entry body.

    Returns:
        The newly created :class:`~agtrk.models.Knowledge`.
    """
    validated_kind = _validate_enum(kind, Kind)
    now = datetime.now().isoformat()

    cursor = conn.execute(
        "INSERT INTO knowledge (repo, kind, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (repo, validated_kind.value, title, content, now, now),
    )
    conn.commit()

    return Knowledge(
        id=cursor.lastrowid,
        repo=repo,
        kind=validated_kind,
        title=title,
        content=content,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------


def recall(
    conn: sqlite3.Connection,
    repo: str,
    kind: str | None = None,
    search: str | None = None,
) -> list[Knowledge]:
    """Look up project knowledge entries.

    Args:
        conn: Open database connection.
        repo: Repository identifier.
        kind: Optional filter by knowledge category.
        search: Optional keyword to match in title or content.

    Returns:
        A list of matching :class:`~agtrk.models.Knowledge` entries.
    """
    conditions = ["repo = ?"]
    params: list[object] = [repo]

    if kind is not None:
        _validate_enum(kind, Kind)
        conditions.append("kind = ?")
        params.append(kind)

    if search is not None:
        pattern = _like_pattern(search)
        conditions.append("(title LIKE ? ESCAPE '\\' COLLATE NOCASE OR content LIKE ? ESCAPE '\\' COLLATE NOCASE)")
        params.extend([pattern, pattern])

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT {_KNOWLEDGE_COLUMNS} FROM knowledge WHERE {where} ORDER BY updated_at DESC",
        params,
    ).fetchall()

    return [_row_to_knowledge(row) for row in rows]


# ---------------------------------------------------------------------------
# get_knowledge
# ---------------------------------------------------------------------------


def get_knowledge(conn: sqlite3.Connection, knowledge_id: int) -> Knowledge:
    """Fetch a single knowledge entry by ID.

    Args:
        conn: Open database connection.
        knowledge_id: The ID of the knowledge entry.

    Returns:
        The :class:`~agtrk.models.Knowledge` entry.

    Raises:
        ValueError: If the entry does not exist.
    """
    row = conn.execute(
        f"SELECT {_KNOWLEDGE_COLUMNS} FROM knowledge WHERE id = ?",
        (knowledge_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No knowledge entry found with id {knowledge_id}")
    return _row_to_knowledge(row)


# ---------------------------------------------------------------------------
# forget
# ---------------------------------------------------------------------------


def forget(conn: sqlite3.Connection, knowledge_id: int) -> int:
    """Delete a knowledge entry.

    Args:
        conn: Open database connection.
        knowledge_id: The ID of the knowledge entry to delete.

    Returns:
        The ID of the deleted entry.

    Raises:
        ValueError: If the entry does not exist.
    """
    cursor = conn.execute("DELETE FROM knowledge WHERE id = ?", (knowledge_id,))
    conn.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"No knowledge entry found with id {knowledge_id}")
    return knowledge_id


# ---------------------------------------------------------------------------
# update_knowledge
# ---------------------------------------------------------------------------


def update_knowledge(
    conn: sqlite3.Connection,
    knowledge_id: int,
    title: str | None = None,
    content: str | None = None,
    kind: str | None = None,
) -> Knowledge:
    """Update a knowledge entry.

    Args:
        conn: Open database connection.
        knowledge_id: The ID of the knowledge entry to update.
        title: New title (optional).
        content: New content (optional).
        kind: New kind (optional).

    Returns:
        The updated :class:`~agtrk.models.Knowledge`.

    Raises:
        ValueError: If the entry does not exist or kind is invalid.
    """
    row = conn.execute(f"SELECT {_KNOWLEDGE_COLUMNS} FROM knowledge WHERE id = ?", (knowledge_id,)).fetchone()
    if row is None:
        raise ValueError(f"No knowledge entry found with id {knowledge_id}")

    if title is None and content is None and kind is None:
        raise ValueError("Nothing to update — provide at least one of: content, --title, --kind")

    if kind is not None:
        _validate_enum(kind, Kind)

    now = datetime.now().isoformat()
    fields: dict[str, object] = {"updated_at": now}
    if title is not None:
        fields["title"] = title
    if content is not None:
        fields["content"] = content
    if kind is not None:
        fields["kind"] = kind

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    values = [*fields.values(), knowledge_id]
    conn.execute(f"UPDATE knowledge SET {set_clause} WHERE id = ?", values)
    conn.commit()

    return Knowledge(
        id=knowledge_id,
        repo=row["repo"],
        kind=Kind(kind if kind is not None else row["kind"]),
        title=title if title is not None else row["title"],
        content=content if content is not None else row["content"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(now),
    )


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


def set_feature(conn: sqlite3.Connection, name: str, enabled: bool) -> None:
    """Enable or disable a feature flag."""
    _validate_enum(name, Feature)
    conn.execute(
        "INSERT INTO feature (name, enabled) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET enabled = excluded.enabled",
        (name, int(enabled)),
    )
    conn.commit()


def is_feature_enabled(conn: sqlite3.Connection, name: str) -> bool:
    """Check if a feature flag is enabled."""
    _validate_enum(name, Feature)
    row = conn.execute("SELECT enabled FROM feature WHERE name = ?", (name,)).fetchone()
    if row is None:
        return False
    return bool(row["enabled"])


def list_features(conn: sqlite3.Connection) -> list[tuple[Feature, bool]]:
    """List all known features with their enabled state.

    Iterates over the Feature enum so newly added members appear
    even without a DB row (defaulting to disabled).
    """
    rows = conn.execute("SELECT name, enabled FROM feature").fetchall()
    db_state = {row["name"]: bool(row["enabled"]) for row in rows}
    return [(f, db_state.get(f.value, False)) for f in Feature]


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------


def delete_session(conn: sqlite3.Connection, id_or_prefix: str) -> str:
    """Delete a session and its notes.

    Args:
        conn: Open database connection.
        id_or_prefix: Exact session id or a unique prefix.

    Returns:
        The id of the deleted session.
    """
    session_id = _resolve_session_id(conn, id_or_prefix)
    conn.execute("DELETE FROM session WHERE id = ?", (session_id,))
    conn.commit()
    return session_id
