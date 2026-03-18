"""Tests for claude_sessions.service"""
import pytest

from claude_sessions.models import Status
from claude_sessions.service import SessionWithNotes, get_session, register_session


class TestRegisterSession:
    def test_creates_session_with_correct_fields(self, db):
        """register_session creates a session with slug, task, repo, and status."""
        session = register_session(db, task="End of Day", repo="my-repo")
        assert session.id == "end-of-day"
        assert session.task == "End of Day"
        assert session.repo == "my-repo"
        assert session.status == Status.planning

    def test_default_status_is_planning(self, db):
        """Default status is 'planning'."""
        session = register_session(db, task="Some Task")
        assert session.status == Status.planning

    def test_with_jira_ticket(self, db):
        """register_session stores jira ticket when provided."""
        session = register_session(db, task="Fix bug", jira="PLAT-1234")
        assert session.jira == "PLAT-1234"

    def test_without_jira_ticket(self, db):
        """register_session sets jira to None when not provided."""
        session = register_session(db, task="Fix bug")
        assert session.jira is None

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

    def test_slug_collision_appends_suffix(self, db):
        """Second registration of same task gets '-2' suffix."""
        first = register_session(db, task="Duplicate Task")
        second = register_session(db, task="Duplicate Task")
        assert first.id == "duplicate-task"
        assert second.id == "duplicate-task-2"

    def test_slug_collision_third_appends_3(self, db):
        """Third registration of same task gets '-3' suffix."""
        register_session(db, task="Triple Task")
        register_session(db, task="Triple Task")
        third = register_session(db, task="Triple Task")
        assert third.id == "triple-task-3"

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
        register_session(db, task="Full ID task")
        result = get_session(db, "full-id-task")
        assert result.id == "full-id-task"
        assert result.task == "Full ID task"

    def test_get_by_unique_prefix(self, db):
        """get_session resolves a unique prefix to the matching session."""
        register_session(db, task="eod day 4")
        result = get_session(db, "eod")
        assert result.id == "eod-day-4"

    def test_get_by_unique_prefix_partial(self, db):
        """get_session resolves an unambiguous partial prefix."""
        register_session(db, task="Feature work alpha")
        result = get_session(db, "feature-work")
        assert result.id == "feature-work-alpha"

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
            db, task="Full fields", repo="my-repo", jira="PLAT-99", status="waiting"
        )
        result = get_session(db, session.id)
        assert result.task == "Full fields"
        assert result.repo == "my-repo"
        assert result.jira == "PLAT-99"
        assert result.status == Status.waiting
