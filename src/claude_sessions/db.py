"""Database access layer for claude-sessions."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "claude-sessions" / "sessions.db"

# ---------------------------------------------------------------------------
# Migrations
# Each entry is a list of SQL statements to execute as one migration step.
# The index + 1 is the resulting schema version after that migration runs.
# ---------------------------------------------------------------------------

MIGRATIONS: list[list[str]] = [
    # Migration 1 — initial schema
    [
        """
        CREATE TABLE IF NOT EXISTS session (
            id           TEXT    PRIMARY KEY,
            task         TEXT    NOT NULL,
            repo         TEXT,
            status       TEXT    NOT NULL DEFAULT 'planning',
            jira         TEXT,
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL,
            completed_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS note (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT    NOT NULL REFERENCES session(id) ON DELETE CASCADE,
            content    TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_note_session_id ON note (session_id)
        """,
    ],
]

DB_SCHEMA_VERSION: int = len(MIGRATIONS)


def get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (and initialise) the SQLite database.

    Resolution order for the database path:
    1. ``CLAUDE_SESSIONS_DB`` environment variable
    2. *db_path* argument
    3. :data:`DEFAULT_DB_PATH`

    The parent directory is created if it does not yet exist.  WAL journal mode
    and foreign-key enforcement are enabled on every connection.  Pending
    migrations are applied before the connection is returned.

    Args:
        db_path: Optional explicit path to the database file.

    Returns:
        An open :class:`sqlite3.Connection` with ``row_factory`` set to
        :attr:`sqlite3.Row`.
    """
    env_path = os.environ.get("CLAUDE_SESSIONS_DB")
    if env_path:
        resolved = Path(env_path)
    elif db_path is not None:
        resolved = db_path
    else:
        resolved = DEFAULT_DB_PATH

    resolved.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    _ensure_schema_version_table(conn)
    _run_migrations(conn)

    return conn


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    """Create schema_version table if absent and seed with 0 if empty."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
        """
    )
    row = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    if row[0] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
    conn.commit()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply any pending migrations and update the stored version."""
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    current_version: int = row[0]

    if current_version >= DB_SCHEMA_VERSION:
        return

    for migration_statements in MIGRATIONS[current_version:]:
        for statement in migration_statements:
            conn.execute(statement)

    conn.execute(
        "UPDATE schema_version SET version = ?", (DB_SCHEMA_VERSION,)
    )
    conn.commit()
