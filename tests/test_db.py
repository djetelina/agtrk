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
