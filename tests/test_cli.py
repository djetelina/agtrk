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


def test_register_todo_skips_repo_autodetect(tmp_db_env):
    """Todo sessions should not auto-detect repo (often cross-repo observations)."""
    result = runner.invoke(app, ["register", "--task", "Noted for later", "--status", "todo"])
    assert result.exit_code == 0
    session_id = _extract_id(result.stdout, "noted-for-later")
    show = runner.invoke(app, ["show", session_id])
    assert show.exit_code == 0
    # Repo line should show '-' (no repo)
    assert "Repo:" in show.stdout
    # Should not have picked up any repo from git
    assert "agtrk" not in show.stdout.split("Repo:")[1].split("\n")[0]


def test_register_todo_with_explicit_repo(tmp_db_env):
    """Even for todo, explicit --repo should be respected."""
    result = runner.invoke(app, ["register", "--task", "Cross repo work", "--status", "todo", "--repo", "other/repo"])
    assert result.exit_code == 0
    session_id = _extract_id(result.stdout, "cross-repo-work")
    show = runner.invoke(app, ["show", session_id])
    assert "repo" in show.stdout.split("Repo:")[1].split("\n")[0]


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


def test_learn(tmp_db_env):
    result = runner.invoke(app, ["learn", "--kind", "architecture", "--title", "API layer", "--repo", "acme/widgets", "REST API in src/api/"])
    assert result.exit_code == 0
    assert "Learned #" in result.stdout
    assert "API layer" in result.stdout


def test_learn_invalid_kind(tmp_db_env):
    result = runner.invoke(app, ["learn", "--kind", "garbage", "--title", "Bad", "--repo", "acme/widgets", "content"])
    assert result.exit_code != 0
    assert "Invalid kind" in result.stdout


def test_recall_empty(tmp_db_env):
    result = runner.invoke(app, ["recall", "--repo", "acme/widgets"])
    assert result.exit_code == 0
    assert "No knowledge entries found" in result.stdout


def test_recall_with_entries(tmp_db_env):
    runner.invoke(app, ["learn", "--kind", "architecture", "--title", "API layer", "--repo", "acme/widgets", "REST"])
    runner.invoke(app, ["learn", "--kind", "decision", "--title", "ORM choice", "--repo", "acme/widgets", "SQLAlchemy"])
    result = runner.invoke(app, ["recall", "--repo", "acme/widgets"])
    assert result.exit_code == 0
    assert "API layer" in result.stdout
    assert "ORM choice" in result.stdout


def test_recall_with_search(tmp_db_env):
    runner.invoke(app, ["learn", "--kind", "architecture", "--title", "API layer", "--repo", "acme/widgets", "REST"])
    runner.invoke(app, ["learn", "--kind", "decision", "--title", "ORM choice", "--repo", "acme/widgets", "SQLAlchemy"])
    result = runner.invoke(app, ["recall", "--repo", "acme/widgets", "--search", "api"])
    assert result.exit_code == 0
    assert "API layer" in result.stdout
    assert "ORM choice" not in result.stdout


def test_recall_with_kind_filter(tmp_db_env):
    runner.invoke(app, ["learn", "--kind", "architecture", "--title", "API layer", "--repo", "acme/widgets", "REST"])
    runner.invoke(app, ["learn", "--kind", "decision", "--title", "ORM choice", "--repo", "acme/widgets", "SQLAlchemy"])
    result = runner.invoke(app, ["recall", "--repo", "acme/widgets", "--kind", "decision"])
    assert result.exit_code == 0
    assert "ORM choice" in result.stdout
    assert "API layer" not in result.stdout


def test_forget(tmp_db_env):
    reg = runner.invoke(app, ["learn", "--kind", "architecture", "--title", "API layer", "--repo", "acme/widgets", "REST"])
    # Extract the ID from "Learned #1: API layer"
    entry_id = reg.stdout.split("#")[1].split(":")[0]
    result = runner.invoke(app, ["forget", entry_id])
    assert result.exit_code == 0
    assert "Forgot knowledge entry" in result.stdout


def test_forget_nonexistent(tmp_db_env):
    result = runner.invoke(app, ["forget", "9999"])
    assert result.exit_code != 0
    assert "No knowledge entry found" in result.stdout


def test_update_knowledge(tmp_db_env):
    reg = runner.invoke(app, ["learn", "--kind", "architecture", "--title", "API layer", "--repo", "acme/widgets", "REST"])
    entry_id = reg.stdout.split("#")[1].split(":")[0]
    result = runner.invoke(app, ["update-knowledge", entry_id, "GraphQL instead"])
    assert result.exit_code == 0
    assert "Updated knowledge entry" in result.stdout


def test_inject_excludes_knowledge_when_disabled(tmp_db_env):
    """Inject output should NOT contain knowledge instructions by default."""
    result = runner.invoke(app, ["inject"])
    assert result.exit_code == 0
    assert "agtrk recall" not in result.stdout
    assert "agtrk learn" not in result.stdout
    assert "Knowledge kinds" not in result.stdout


def test_inject_includes_knowledge_when_enabled(tmp_db_env):
    """Inject output should contain knowledge instructions when feature is enabled."""
    runner.invoke(app, ["feature", "enable", "knowledge"])
    result = runner.invoke(app, ["inject"])
    assert result.exit_code == 0
    assert "agtrk recall" in result.stdout
    assert "agtrk learn" in result.stdout
    assert "Knowledge kinds" in result.stdout
    assert "MUST save them" in result.stdout


def test_uninstall_idempotent(tmp_db_env, tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"hooks": {}, "permissions": {"allow": []}}))

    result = runner.invoke(app, ["uninstall", "--settings", str(settings_path)])
    assert result.exit_code == 0


def test_feature_enable(tmp_db_env):
    result = runner.invoke(app, ["feature", "enable", "knowledge"])
    assert result.exit_code == 0
    assert "Enabled feature: knowledge" in result.stdout


def test_feature_disable(tmp_db_env):
    runner.invoke(app, ["feature", "enable", "knowledge"])
    result = runner.invoke(app, ["feature", "disable", "knowledge"])
    assert result.exit_code == 0
    assert "Disabled feature: knowledge" in result.stdout


def test_feature_enable_invalid(tmp_db_env):
    result = runner.invoke(app, ["feature", "enable", "garbage"])
    assert result.exit_code != 0
    assert "Invalid feature" in result.stdout


def test_feature_disable_invalid(tmp_db_env):
    result = runner.invoke(app, ["feature", "disable", "garbage"])
    assert result.exit_code != 0
    assert "Invalid feature" in result.stdout


def test_feature_list(tmp_db_env):
    result = runner.invoke(app, ["feature", "list"])
    assert result.exit_code == 0
    assert "knowledge" in result.stdout
    assert "disabled" in result.stdout.lower()


def test_feature_list_shows_enabled(tmp_db_env):
    runner.invoke(app, ["feature", "enable", "knowledge"])
    result = runner.invoke(app, ["feature", "list"])
    assert result.exit_code == 0
    assert "enabled" in result.stdout.lower()
