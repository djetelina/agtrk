"""Integration tests for the CLI commands."""
import pytest
from typer.testing import CliRunner

from claude_sessions.cli import app

runner = CliRunner()


def test_register(tmp_db_env):
    result = runner.invoke(app, ["register", "--task", "EoD Day 4"])
    assert result.exit_code == 0
    assert "eod-day-4" in result.stdout


def test_register_with_explicit_repo(tmp_db_env):
    result = runner.invoke(app, ["register", "--task", "Explicit repo test", "--repo", "my-repo"])
    assert result.exit_code == 0


def test_register_with_status(tmp_db_env):
    result = runner.invoke(app, ["register", "--task", "Fix test", "--status", "todo"])
    assert result.exit_code == 0


def test_list_empty(tmp_db_env):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No active sessions" in result.stdout


def test_list_with_sessions(tmp_db_env):
    runner.invoke(app, ["register", "--task", "First task"])
    runner.invoke(app, ["register", "--task", "Second task"])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "First task" in result.stdout
    assert "Second task" in result.stdout


def test_show(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "My session"])
    # Extract the session ID from the output
    session_id = None
    for word in reg.stdout.split():
        if "my-session" in word:
            session_id = word.strip()
            break
    assert session_id is not None, f"Could not find session id in: {reg.stdout}"

    runner.invoke(app, ["update", session_id, "--note", "Some progress made"])
    result = runner.invoke(app, ["show", session_id])
    assert result.exit_code == 0
    assert "My session" in result.stdout
    assert "Some progress made" in result.stdout


def test_update(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Update me"])
    session_id = None
    for word in reg.stdout.split():
        if "update-me" in word:
            session_id = word.strip()
            break
    assert session_id is not None

    result = runner.invoke(app, ["update", session_id, "--status", "implementing", "--note", "started"])
    assert result.exit_code == 0


def test_heartbeat(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Heartbeat task"])
    session_id = None
    for word in reg.stdout.split():
        if "heartbeat-task" in word:
            session_id = word.strip()
            break
    assert session_id is not None

    result = runner.invoke(app, ["heartbeat", session_id])
    assert result.exit_code == 0


def test_complete(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Complete me"])
    session_id = None
    for word in reg.stdout.split():
        if "complete-me" in word:
            session_id = word.strip()
            break
    assert session_id is not None

    runner.invoke(app, ["complete", session_id])

    list_result = runner.invoke(app, ["list"])
    assert "Complete me" not in list_result.stdout

    archived_result = runner.invoke(app, ["list", "--archived"])
    assert "Complete me" in archived_result.stdout


def test_reopen(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Reopen me"])
    session_id = None
    for word in reg.stdout.split():
        if "reopen-me" in word:
            session_id = word.strip()
            break
    assert session_id is not None

    runner.invoke(app, ["complete", session_id])
    runner.invoke(app, ["reopen", session_id])

    list_result = runner.invoke(app, ["list"])
    assert "Reopen me" in list_result.stdout


def test_not_found(tmp_db_env):
    result = runner.invoke(app, ["show", "nonexistent"])
    assert result.exit_code != 0
