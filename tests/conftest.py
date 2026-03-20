"""Shared pytest fixtures for claude-sessions tests."""
import subprocess
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


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Create a git repo with one commit, cd into it."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def git_repo_with_remote(git_repo):
    """Add an HTTPS-style origin remote to git_repo."""
    subprocess.run(
        ["git", "-C", str(git_repo), "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        check=True, capture_output=True,
    )
    return git_repo
