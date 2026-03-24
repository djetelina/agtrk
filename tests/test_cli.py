"""Integration tests for the CLI commands."""

import json

import pytest
from typer.testing import CliRunner

from agtrk.cli import app

runner = CliRunner()


def _extract_id(output: str, slug_prefix: str) -> str:
    """Extract a session ID containing slug_prefix from CLI output."""
    for word in output.split():
        if slug_prefix in word:
            return word.strip()
    raise AssertionError(f"Could not find '{slug_prefix}' in: {output}")


def test_register(tmp_db_env):
    result = runner.invoke(app, ["register", "--task", "Fix login bug"])
    assert result.exit_code == 0
    assert "fix-login-bug" in result.stdout


def test_register_with_explicit_repo(tmp_db_env):
    result = runner.invoke(app, ["register", "--task", "Explicit repo test", "--repo", "my-repo"])
    assert result.exit_code == 0


def test_register_with_status(tmp_db_env):
    result = runner.invoke(app, ["register", "--task", "Fix test", "--status", "todo"])
    assert result.exit_code == 0


def test_register_invalid_status(tmp_db_env):
    result = runner.invoke(app, ["register", "--task", "Bad status", "--status", "garbage"])
    assert result.exit_code != 0
    assert "Invalid status" in result.stdout


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
    session_id = _extract_id(reg.stdout, "my-session")

    runner.invoke(app, ["update", session_id, "--note", "Some progress made"])
    result = runner.invoke(app, ["show", session_id])
    assert result.exit_code == 0
    assert "My session" in result.stdout
    assert "Some progress made" in result.stdout


def test_update(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Update me"])
    session_id = _extract_id(reg.stdout, "update-me")

    result = runner.invoke(app, ["update", session_id, "--status", "implementing", "--note", "started"])
    assert result.exit_code == 0
    assert "Updated session:" in result.stdout


def test_heartbeat(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Heartbeat task"])
    session_id = _extract_id(reg.stdout, "heartbeat-task")

    result = runner.invoke(app, ["heartbeat", session_id])
    assert result.exit_code == 0


def test_complete(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Complete me"])
    session_id = _extract_id(reg.stdout, "complete-me")

    runner.invoke(app, ["complete", session_id])

    list_result = runner.invoke(app, ["list"])
    assert "Complete me" not in list_result.stdout

    archived_result = runner.invoke(app, ["list", "--archived"])
    assert "Complete me" in archived_result.stdout


def test_reopen(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Reopen me"])
    session_id = _extract_id(reg.stdout, "reopen-me")

    runner.invoke(app, ["complete", session_id])
    runner.invoke(app, ["reopen", session_id])

    list_result = runner.invoke(app, ["list"])
    assert "Reopen me" in list_result.stdout


def test_delete(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Delete me"])
    session_id = _extract_id(reg.stdout, "delete-me")

    result = runner.invoke(app, ["delete", session_id])
    assert result.exit_code == 0
    assert "Deleted session:" in result.stdout

    list_result = runner.invoke(app, ["list", "--all"])
    assert "Delete me" not in list_result.stdout


def test_search(tmp_db_env):
    reg = runner.invoke(app, ["register", "--task", "Auth migration"])
    session_id = _extract_id(reg.stdout, "auth-migration")
    runner.invoke(app, ["update", session_id, "--note", "deployed new auth flow"])
    result = runner.invoke(app, ["search", "auth"])
    assert result.exit_code == 0
    assert "auth-migration" in result.stdout
    assert "deployed new auth flow" in result.stdout


def test_search_no_results(tmp_db_env):
    result = runner.invoke(app, ["search", "nonexistent"])
    assert result.exit_code == 0
    assert "No matches" in result.stdout


def test_not_found(tmp_db_env):
    result = runner.invoke(app, ["show", "nonexistent"])
    assert result.exit_code != 0


def test_inject_empty(tmp_db_env):
    result = runner.invoke(app, ["inject"])
    assert result.exit_code == 0
    assert "no active sessions" in result.stdout
    assert "agtrk update" in result.stdout


def test_inject_with_sessions(tmp_db_env):
    runner.invoke(app, ["register", "--task", "Active work"])
    result = runner.invoke(app, ["inject"])
    assert result.exit_code == 0
    assert "Active work" in result.stdout
    assert "agtrk show <id>" in result.stdout
    assert "agtrk register" in result.stdout
    assert "agtrk update" in result.stdout
    assert "agtrk complete" in result.stdout
    assert "agtrk heartbeat" in result.stdout
    assert "*/30" in result.stdout
    assert "future session" in result.stdout


def test_install_fresh(tmp_db_env, tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{}")

    result = runner.invoke(app, ["install", "--settings", str(settings_path)])
    assert result.exit_code == 0

    settings = json.loads(settings_path.read_text())
    hooks = settings["hooks"]
    assert "SessionStart" in hooks
    assert "PreCompact" in hooks
    for event in ("SessionStart", "PreCompact"):
        cmds = [h["command"] for entry in hooks[event] for h in entry["hooks"]]
        assert any("agtrk inject" in c for c in cmds)
    assert "Bash(agtrk:*)" in settings["permissions"]["allow"]


def test_install_idempotent(tmp_db_env, tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "agtrk inject", "timeout": 10}]}]},
                "permissions": {"allow": ["Bash(agtrk:*)"]},
            }
        )
    )

    result = runner.invoke(app, ["install", "--settings", str(settings_path)])
    assert result.exit_code == 0

    settings = json.loads(settings_path.read_text())
    agtrk_entries = [entry for entry in settings["hooks"]["SessionStart"] for h in entry["hooks"] if "agtrk inject" in h["command"]]
    assert len(agtrk_entries) == 1
    assert "PreCompact" in settings["hooks"]
    assert settings["permissions"]["allow"].count("Bash(agtrk:*)") == 1


def test_install_preserves_other_hooks(tmp_db_env, tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "some-other-tool prime"}]}]}}))

    result = runner.invoke(app, ["install", "--settings", str(settings_path)])
    assert result.exit_code == 0

    settings = json.loads(settings_path.read_text())
    cmds = [h["command"] for entry in settings["hooks"]["SessionStart"] for h in entry["hooks"]]
    assert "some-other-tool prime" in cmds
    assert any("agtrk inject" in c for c in cmds)


def test_uninstall(tmp_db_env, tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    # Start with a fully installed state plus other hooks
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "some-other-tool prime"}]},
                        {"hooks": [{"type": "command", "command": "agtrk inject", "timeout": 10}]},
                    ],
                    "PreCompact": [
                        {"hooks": [{"type": "command", "command": "agtrk inject", "timeout": 10}]},
                    ],
                },
                "permissions": {"allow": ["Read", "Bash(agtrk:*)", "Grep"]},
            }
        )
    )

    result = runner.invoke(app, ["uninstall", "--settings", str(settings_path)])
    assert result.exit_code == 0

    settings = json.loads(settings_path.read_text())
    # agtrk hooks removed, other hooks preserved
    cmds = [h["command"] for entry in settings["hooks"]["SessionStart"] for h in entry["hooks"]]
    assert "some-other-tool prime" in cmds
    assert not any("agtrk inject" in c for c in cmds)
    # PreCompact should be empty or gone
    pre_compact_cmds = [h["command"] for entry in settings["hooks"].get("PreCompact", []) for h in entry["hooks"]]
    assert not any("agtrk inject" in c for c in pre_compact_cmds)
    # Permission removed, others preserved
    assert "Bash(agtrk:*)" not in settings["permissions"]["allow"]
    assert "Read" in settings["permissions"]["allow"]
    assert "Grep" in settings["permissions"]["allow"]


def test_uninstall_idempotent(tmp_db_env, tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"hooks": {}, "permissions": {"allow": []}}))

    result = runner.invoke(app, ["uninstall", "--settings", str(settings_path)])
    assert result.exit_code == 0
