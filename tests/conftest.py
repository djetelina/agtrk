"""Shared pytest fixtures for claude-sessions tests."""
import os
from pathlib import Path

import pytest

from claude_sessions.db import get_db


@pytest.fixture
def tmp_db(tmp_path):
    """Return a Path to a temp database file (does not create it)."""
    return tmp_path / "test_sessions.db"


@pytest.fixture
def db(tmp_db):
    """Return an initialized sqlite3.Connection via get_db(tmp_db)."""
    conn = get_db(tmp_db)
    yield conn
    conn.close()


@pytest.fixture
def tmp_db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set env var so CLI uses a temp database."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("CLAUDE_SESSIONS_DB", str(db_file))
