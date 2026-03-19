"""Tests for claude_sessions.db"""
import sqlite3

import pytest

from claude_sessions.db import DB_SCHEMA_VERSION, get_db


class TestSchemaCreation:
    def test_creates_db_file(self, tmp_db):
        """get_db creates the database file."""
        assert not tmp_db.exists()
        conn = get_db(tmp_db)
        conn.close()
        assert tmp_db.exists()

    def test_creates_session_table(self, db):
        """session table exists after get_db."""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session'"
        ).fetchone()
        assert row is not None

    def test_creates_note_table(self, db):
        """note table exists after get_db."""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='note'"
        ).fetchone()
        assert row is not None

    def test_creates_schema_version_table(self, db):
        """schema_version table exists after get_db."""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        assert row is not None

    def test_schema_version_is_current(self, db):
        """schema_version table holds the current DB_SCHEMA_VERSION."""
        row = db.execute("SELECT version FROM schema_version").fetchone()
        assert row is not None
        assert row[0] == DB_SCHEMA_VERSION

    def test_wal_mode_enabled(self, db):
        """journal_mode is wal after get_db."""
        row = db.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_idempotent_get_db(self, tmp_db):
        """Reopening an existing db with get_db preserves existing data."""
        conn = get_db(tmp_db)
        conn.execute(
            "INSERT INTO session (id, task, status, created_at, updated_at) "
            "VALUES ('test-id', 'Test Task', 'planning', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
        conn.commit()
        conn.close()

        conn2 = get_db(tmp_db)
        row = conn2.execute(
            "SELECT id FROM session WHERE id='test-id'"
        ).fetchone()
        conn2.close()
        assert row is not None
        assert row[0] == "test-id"


class TestMigration2:
    def test_note_has_context_columns(self, db):
        """Migration 2 adds repo, branch, cwd, worktree columns to note table."""
        cursor = db.execute("PRAGMA table_info(note)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "repo" in columns
        assert "branch" in columns
        assert "cwd" in columns
        assert "worktree" in columns

    def test_migration_from_v1_to_v2(self, tmp_db):
        """Existing v1 database gets migrated to v2 with new note columns."""
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(tmp_db))
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("""
            CREATE TABLE session (
                id TEXT PRIMARY KEY, task TEXT NOT NULL, repo TEXT,
                status TEXT NOT NULL DEFAULT 'planning', jira TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE note (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
                content TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX idx_note_session_id ON note (session_id)")
        conn.commit()
        conn.close()

        conn = get_db(tmp_db)
        cursor = conn.execute("PRAGMA table_info(note)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "repo" in columns
        assert "branch" in columns
        assert "cwd" in columns
        assert "worktree" in columns

        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert version == DB_SCHEMA_VERSION
        conn.close()


class TestMigration:
    def test_migration_runs_on_old_schema(self, tmp_db):
        """Manually create schema_version at version=0, then get_db migrates to current."""
        # Bootstrap a minimal db with only the schema_version table at version 0
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "CREATE TABLE schema_version (version INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        conn.commit()
        conn.close()

        # Now call get_db — it should run all pending migrations
        conn = get_db(tmp_db)

        version_row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert version_row[0] == DB_SCHEMA_VERSION

        # Verify tables were created by migration
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "session" in tables
        assert "note" in tables

        conn.close()
