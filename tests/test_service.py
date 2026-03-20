"""Tests for claude_sessions.service"""
import subprocess

import pytest

from claude_sessions.models import Session, Status
from claude_sessions.service import (
    SessionWithNotes,
    cleanup,
    complete_session,
    get_session,
    heartbeat,
    list_sessions,
    register_session,
    reopen_session,
    update_session,
)


class TestRegisterSession:
    def test_creates_session_with_correct_fields(self, db):
        """register_session creates a session with slug, task, repo, and status."""
        session = register_session(db, task="End of Day", repo="my-repo")
        assert session.id.startswith("end-of-day-")
        assert session.task == "End of Day"
        assert session.repo == "my-repo"
        assert session.status == Status.planning

    def test_default_status_is_planning(self, db):
        """Default status is 'planning'."""
        session = register_session(db, task="Some Task")
        assert session.status == Status.planning

    def test_with_issue(self, db):
        """register_session stores issue when provided."""
        session = register_session(db, task="Fix bug", issue="PLAT-1234")
        assert session.issue == "PLAT-1234"

    def test_without_issue(self, db):
        """register_session sets issue to None when not provided."""
        session = register_session(db, task="Fix bug")
        assert session.issue is None

    def test_with_initial_note(self, db):
        """register_session with note= stores a note, visible via get_session."""
        session = register_session(db, task="Task with note", note="Initial handoff")
        result = get_session(db, session.id)
        assert len(result.notes) == 1
        assert result.notes[0].content == "Initial handoff"

    def test_without_initial_note(self, db):
        """register_session without note= results in empty notes list."""
        session = register_session(db, task="No note task")
        result = get_session(db, session.id)
        assert result.notes == []

    def test_multiple_same_task_get_unique_ids(self, db):
        """Multiple registrations of same task get unique IDs."""
        first = register_session(db, task="Duplicate Task")
        second = register_session(db, task="Duplicate Task")
        third = register_session(db, task="Duplicate Task")
        assert first.id != second.id
        assert second.id != third.id
        assert first.id.startswith("duplicate-task-")
        assert second.id.startswith("duplicate-task-")
        assert third.id.startswith("duplicate-task-")

    def test_custom_status(self, db):
        """register_session accepts non-default status."""
        session = register_session(db, task="Implementing stuff", status="implementing")
        assert session.status == Status.implementing

    def test_persists_to_db(self, db):
        """Registered session is queryable from the database."""
        session = register_session(db, task="Persist me", repo="repo-x")
        row = db.execute(
            "SELECT id, task, repo FROM session WHERE id = ?", (session.id,)
        ).fetchone()
        assert row is not None
        assert row["task"] == "Persist me"
        assert row["repo"] == "repo-x"


class TestGetSession:
    def test_get_by_full_id(self, db):
        """get_session returns session when given the exact id."""
        session = register_session(db, task="Full ID task")
        result = get_session(db, session.id)
        assert result.id == session.id
        assert result.task == "Full ID task"

    def test_get_by_unique_prefix(self, db):
        """get_session resolves a unique prefix to the matching session."""
        session = register_session(db, task="eod day 4")
        result = get_session(db, "eod")
        assert result.id == session.id

    def test_get_by_unique_prefix_partial(self, db):
        """get_session resolves an unambiguous partial prefix."""
        session = register_session(db, task="Feature work alpha")
        result = get_session(db, "feature-work")
        assert result.id == session.id

    def test_ambiguous_prefix_raises_value_error(self, db):
        """Ambiguous prefix raises ValueError with 'Ambiguous' in message."""
        register_session(db, task="Alpha task one")
        register_session(db, task="Alpha task two")
        with pytest.raises(ValueError, match="Ambiguous"):
            get_session(db, "alpha")

    def test_not_found_raises_value_error(self, db):
        """Non-existent id or prefix raises ValueError with 'No session found'."""
        with pytest.raises(ValueError, match="No session found"):
            get_session(db, "nonexistent-session")

    def test_returns_session_with_notes(self, db):
        """get_session returns a SessionWithNotes instance."""
        session = register_session(db, task="Notes session", note="First note")
        result = get_session(db, session.id)
        assert isinstance(result, SessionWithNotes)
        assert len(result.notes) == 1
        assert result.notes[0].content == "First note"

    def test_returns_notes_ordered_by_created_at(self, db):
        """Notes are returned ordered by created_at ascending."""
        session = register_session(db, task="Ordered notes")
        # Insert extra notes directly to control ordering test
        import sqlite3
        db.execute(
            "INSERT INTO note (session_id, content, created_at) VALUES (?, ?, ?)",
            (session.id, "Note B", "2026-01-01T10:00:00"),
        )
        db.execute(
            "INSERT INTO note (session_id, content, created_at) VALUES (?, ?, ?)",
            (session.id, "Note A", "2026-01-01T09:00:00"),
        )
        db.commit()
        result = get_session(db, session.id)
        assert result.notes[0].content == "Note A"
        assert result.notes[1].content == "Note B"

    def test_session_without_notes_has_empty_list(self, db):
        """get_session on a session without notes returns empty notes list."""
        session = register_session(db, task="Empty notes")
        result = get_session(db, session.id)
        assert result.notes == []

    def test_returns_all_session_fields(self, db):
        """get_session returns all Session fields on the SessionWithNotes object."""
        session = register_session(
            db, task="Full fields", repo="my-repo", issue="PLAT-99", status="waiting"
        )
        result = get_session(db, session.id)
        assert result.task == "Full fields"
        assert result.repo == "my-repo"
        assert result.issue == "PLAT-99"
        assert result.status == Status.waiting


class TestUpdateSession:
    def test_update_status(self, db):
        """update_session changes status to implementing."""
        session = register_session(db, task="Status task")
        updated = update_session(db, session.id, status="implementing")
        assert isinstance(updated, Session)
        assert updated.status == Status.implementing

    def test_update_appends_note(self, db):
        """update_session with note= stores a note visible via get_session."""
        session = register_session(db, task="Note task")
        update_session(db, session.id, note="Progress update")
        result = get_session(db, session.id)
        assert len(result.notes) == 1
        assert result.notes[0].content == "Progress update"

    def test_update_multiple_notes(self, db):
        """Two updates with notes produce 2 notes in timeline."""
        session = register_session(db, task="Multi note task")
        update_session(db, session.id, note="First note")
        update_session(db, session.id, note="Second note")
        result = get_session(db, session.id)
        assert len(result.notes) == 2
        contents = [n.content for n in result.notes]
        assert "First note" in contents
        assert "Second note" in contents

    def test_update_bumps_timestamp(self, db):
        """updated_at increases after update."""
        import time
        session = register_session(db, task="Timestamp task")
        before = session.updated_at
        time.sleep(0.01)
        updated = update_session(db, session.id, status="implementing")
        assert updated.updated_at >= before

    def test_update_issue(self, db):
        """update_session sets issue field."""
        session = register_session(db, task="Jira task")
        updated = update_session(db, session.id, issue="PLAT-9999")
        assert updated.issue == "PLAT-9999"

    def test_update_repo(self, db):
        """update_session sets repo field."""
        session = register_session(db, task="Repo task")
        updated = update_session(db, session.id, repo="new-repo")
        assert updated.repo == "new-repo"

    def test_update_task_description(self, db):
        """update_session changes task text."""
        session = register_session(db, task="Old task description")
        updated = update_session(db, session.id, task="New task description")
        assert updated.task == "New task description"


class TestHeartbeat:
    def test_heartbeat_bumps_timestamp(self, db):
        """heartbeat updates updated_at."""
        import time
        session = register_session(db, task="Heartbeat task")
        before = session.updated_at
        time.sleep(0.01)
        result = heartbeat(db, session.id)
        assert isinstance(result, Session)
        assert result.updated_at >= before

    def test_heartbeat_does_not_change_fields(self, db):
        """heartbeat leaves task, repo, status unchanged."""
        session = register_session(
            db, task="Stable task", repo="stable-repo", status="waiting"
        )
        result = heartbeat(db, session.id)
        assert result.task == "Stable task"
        assert result.repo == "stable-repo"
        assert result.status == Status.waiting


class TestCompleteSession:
    def test_complete_sets_done(self, db):
        """complete_session sets status=done and completed_at is not None."""
        session = register_session(db, task="Complete task")
        result = complete_session(db, session.id)
        assert isinstance(result, Session)
        assert result.status == Status.done
        assert result.completed_at is not None


class TestReopenSession:
    def test_reopen_clears_completion(self, db):
        """reopen_session sets completed_at=None and status=implementing by default."""
        session = register_session(db, task="Reopen task")
        complete_session(db, session.id)
        result = reopen_session(db, session.id)
        assert isinstance(result, Session)
        assert result.completed_at is None
        assert result.status == Status.implementing

    def test_reopen_with_custom_status(self, db):
        """reopen_session with status='waiting' sets status to waiting."""
        session = register_session(db, task="Custom reopen task")
        complete_session(db, session.id)
        result = reopen_session(db, session.id, status="waiting")
        assert result.status == Status.waiting
        assert result.completed_at is None


class TestListSessions:
    def test_list_active_sessions(self, db):
        """Default list returns only active (not completed) sessions."""
        s1 = register_session(db, task="Active one")
        s2 = register_session(db, task="Active two")
        s3 = register_session(db, task="Completed one")
        complete_session(db, s3.id)

        results = list_sessions(db)
        assert len(results) == 2
        ids = {s.id for s in results}
        assert s1.id in ids
        assert s2.id in ids

    def test_list_archived_only(self, db):
        """archived_only=True returns only completed sessions."""
        register_session(db, task="Still active")
        s2 = register_session(db, task="Archived one")
        complete_session(db, s2.id)

        results = list_sessions(db, archived_only=True)
        assert len(results) == 1
        assert results[0].id == s2.id

    def test_list_all(self, db):
        """include_archived=True returns all sessions."""
        register_session(db, task="Active session")
        s2 = register_session(db, task="Done session")
        complete_session(db, s2.id)

        results = list_sessions(db, include_archived=True)
        assert len(results) == 2

    def test_list_empty(self, db):
        """Empty database returns empty list."""
        results = list_sessions(db)
        assert results == []


class TestCleanup:
    def test_cleanup_removes_old_archived(self, db):
        """Archived sessions older than threshold are deleted."""
        s = register_session(db, task="Old done task")
        complete_session(db, s.id)
        old_date = "2025-01-01T00:00:00"
        db.execute(
            "UPDATE session SET completed_at = ? WHERE id = ?", (old_date, s.id)
        )
        db.commit()

        count = cleanup(db, older_than_days=30)
        assert count == 1
        row = db.execute("SELECT id FROM session WHERE id = ?", (s.id,)).fetchone()
        assert row is None

    def test_cleanup_keeps_recent_archived(self, db):
        """Archived sessions completed recently are not deleted."""
        s = register_session(db, task="Recent done task")
        complete_session(db, s.id)

        count = cleanup(db, older_than_days=30)
        assert count == 0
        row = db.execute("SELECT id FROM session WHERE id = ?", (s.id,)).fetchone()
        assert row is not None

    def test_cleanup_keeps_active(self, db):
        """Active sessions with old updated_at are not deleted by cleanup."""
        s = register_session(db, task="Old active task")
        old_date = "2025-01-01T00:00:00"
        db.execute(
            "UPDATE session SET updated_at = ? WHERE id = ?", (old_date, s.id)
        )
        db.commit()

        count = cleanup(db, older_than_days=30)
        assert count == 0
        row = db.execute("SELECT id FROM session WHERE id = ?", (s.id,)).fetchone()
        assert row is not None

    def test_cleanup_deletes_notes_too(self, db):
        """Cleanup of an archived session also removes its notes (CASCADE)."""
        s = register_session(db, task="Session with notes", note="A note")
        complete_session(db, s.id)
        old_date = "2025-01-01T00:00:00"
        db.execute(
            "UPDATE session SET completed_at = ? WHERE id = ?", (old_date, s.id)
        )
        db.commit()

        count = cleanup(db, older_than_days=30)
        assert count == 1
        note_rows = db.execute(
            "SELECT id FROM note WHERE session_id = ?", (s.id,)
        ).fetchall()
        assert note_rows == []


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Create a git repo with an origin remote, cd into it."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        check=True, capture_output=True,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    return tmp_path


class TestNoteAutoDetection:
    def test_register_note_gets_git_context(self, db, git_repo):
        """Note created via register picks up repo/branch/cwd/worktree."""
        session = register_session(db, task="Auto note", note="initial")
        result = get_session(db, session.id)
        note = result.notes[0]
        assert note.repo == "acme/widgets"
        assert note.branch is not None
        assert note.cwd is not None
        assert note.worktree is False

    def test_update_note_gets_git_context(self, db, git_repo):
        """Note created via update picks up repo/branch/cwd/worktree."""
        session = register_session(db, task="Update auto")
        update_session(db, session.id, note="progress")
        result = get_session(db, session.id)
        note = result.notes[0]
        assert note.repo == "acme/widgets"
        assert note.branch is not None

    def test_note_branch_override(self, db, git_repo):
        """Explicit branch overrides auto-detected value."""
        session = register_session(db, task="Branch override")
        update_session(db, session.id, note="custom branch", branch="custom/branch")
        result = get_session(db, session.id)
        note = result.notes[0]
        assert note.branch == "custom/branch"

    def test_note_without_git_repo(self, db, tmp_path, monkeypatch):
        """Notes still work when not in a git repo."""
        monkeypatch.chdir(tmp_path)
        session = register_session(db, task="No git")
        update_session(db, session.id, note="still works")
        result = get_session(db, session.id)
        note = result.notes[0]
        assert note.repo is None
        assert note.branch is None
        assert note.cwd is not None
        assert note.worktree is None
