"""Database access layer for agtrk."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from platformdirs import user_data_dir

DEFAULT_DB_PATH = Path(user_data_dir("agtrk")) / "sessions.db"

_LEGACY_PATHS = [
    # Most recent legacy: hardcoded ~/.local/share/agtrk (pre-platformdirs)
    Path.home() / ".local" / "share" / "agtrk" / "sessions.db",
    # Oldest legacy: original claude-sessions name
    Path.home() / ".local" / "share" / "claude-sessions" / "sessions.db",
]

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
    # Migration 2 — note context fields
    [
        "ALTER TABLE note ADD COLUMN repo TEXT",
        "ALTER TABLE note ADD COLUMN branch TEXT",
        "ALTER TABLE note ADD COLUMN cwd TEXT",
        "ALTER TABLE note ADD COLUMN worktree INTEGER",
    ],
    # Migration 3 — rename jira to issue
    [
        "ALTER TABLE session RENAME COLUMN jira TO issue",
    ],
    # Migration 4 — session summary
    [
        "ALTER TABLE session ADD COLUMN summary TEXT",
    ],
    # Migration 5 — knowledge table
    [
        """
        CREATE TABLE IF NOT EXISTS knowledge (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            repo       TEXT    NOT NULL,
            kind       TEXT    NOT NULL,
            title      TEXT    NOT NULL,
            content    TEXT    NOT NULL,
            created_at TEXT    NOT NULL,
            updated_at TEXT    NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_repo ON knowledge (repo)
        """,
    ],
    # Migration 6 — feature flags table
    [
        """
        CREATE TABLE IF NOT EXISTS feature (
            name    TEXT    PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0
        )
        """,
    ],
]

DB_SCHEMA_VERSION: int = len(MIGRATIONS)


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (and initialise) the SQLite database.

    Resolution order for the database path:
    1. ``AGTRK_DB`` environment variable
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
    env_path = os.environ.get("AGTRK_DB")
    if env_path:
        resolved = Path(env_path)
    elif db_path is not None:
        resolved = db_path
    else:
        resolved = DEFAULT_DB_PATH
        if not resolved.exists():
            for legacy in _LEGACY_PATHS:
                if legacy.exists():
                    resolved.parent.mkdir(parents=True, exist_ok=True)
                    legacy.rename(resolved)
                    break

    resolved.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    _ensure_schema_version_table(conn)
    _run_migrations(conn)

    return conn


@contextmanager
def open_db(db_path: Path | None = None):
    """Context manager that opens a DB connection and ensures it is closed."""
    conn = get_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


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

    conn.execute("UPDATE schema_version SET version = ?", (DB_SCHEMA_VERSION,))
    conn.commit()
