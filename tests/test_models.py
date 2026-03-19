"""Tests for claude_sessions.models"""
from datetime import datetime

import pytest

from claude_sessions.models import Note, Session, Status, generate_slug


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class TestStatus:
    def test_values(self):
        assert Status.todo == "todo"
        assert Status.planning == "planning"
        assert Status.implementing == "implementing"
        assert Status.waiting == "waiting"
        assert Status.done == "done"

    def test_is_str(self):
        """StrEnum instances must behave as plain strings."""
        assert isinstance(Status.todo, str)
        assert isinstance(Status.implementing, str)

    def test_all_values(self):
        values = {s.value for s in Status}
        assert values == {"todo", "planning", "implementing", "waiting", "done"}


# ---------------------------------------------------------------------------
# generate_slug
# ---------------------------------------------------------------------------

class TestGenerateSlug:
    def test_basic(self):
        assert generate_slug("EoD Day 4") == "eod-day-4"

    def test_special_chars(self):
        assert generate_slug("Fix bug #123 (urgent!)") == "fix-bug-123-urgent"

    def test_truncation(self):
        long_input = "a" * 60
        result = generate_slug(long_input)
        assert len(result) <= 20

    def test_leading_trailing_hyphens_stripped(self):
        assert generate_slug("--hello world--") == "hello-world"

    def test_collision_single(self):
        result = generate_slug("EoD Day 4", existing_slugs={"eod-day-4"})
        assert result == "eod-day-4-2"

    def test_collision_multiple(self):
        existing = {"eod-day-4", "eod-day-4-2", "eod-day-4-3"}
        result = generate_slug("EoD Day 4", existing_slugs=existing)
        assert result == "eod-day-4-4"

    def test_no_collision_when_empty(self):
        result = generate_slug("EoD Day 4", existing_slugs=set())
        assert result == "eod-day-4"

    def test_no_collision_when_none(self):
        result = generate_slug("EoD Day 4", existing_slugs=None)
        assert result == "eod-day-4"


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------

class TestSession:
    def _make(self, **overrides):
        now = datetime(2026, 3, 18, 12, 0, 0)
        defaults = dict(
            id="eod-day-4",
            task="EoD Day 4",
            repo="some-repo",
            status=Status.planning,
            jira="PLAT-1234",
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        defaults.update(overrides)
        return Session(**defaults)

    def test_basic_creation(self):
        s = self._make()
        assert s.id == "eod-day-4"
        assert s.task == "EoD Day 4"
        assert s.repo == "some-repo"
        assert s.status == Status.planning
        assert s.jira == "PLAT-1234"
        assert s.completed_at is None

    def test_repo_optional(self):
        s = self._make(repo=None)
        assert s.repo is None

    def test_jira_optional(self):
        s = self._make(jira=None)
        assert s.jira is None

    def test_completed_at_optional(self):
        now = datetime(2026, 3, 18, 12, 0, 0)
        s = self._make(completed_at=now)
        assert s.completed_at == now

    def test_status_is_status_enum(self):
        s = self._make(status=Status.implementing)
        assert s.status == Status.implementing
        assert isinstance(s.status, str)


# ---------------------------------------------------------------------------
# Note dataclass
# ---------------------------------------------------------------------------

class TestNote:
    def _make(self, **overrides):
        now = datetime(2026, 3, 18, 12, 0, 0)
        defaults = dict(
            id=1,
            session_id="eod-day-4",
            content="Some note content",
            created_at=now,
            repo=None,
            branch=None,
            cwd=None,
            worktree=None,
        )
        defaults.update(overrides)
        return Note(**defaults)

    def test_basic_creation(self):
        n = self._make()
        assert n.id == 1
        assert n.session_id == "eod-day-4"
        assert n.content == "Some note content"

    def test_id_is_int(self):
        n = self._make(id=42)
        assert n.id == 42
        assert isinstance(n.id, int)

    def test_created_at(self):
        now = datetime(2026, 3, 18, 12, 0, 0)
        n = self._make(created_at=now)
        assert n.created_at == now

    def test_context_fields(self):
        n = self._make(repo="acme/widgets", branch="main", cwd="projects/widgets", worktree=False)
        assert n.repo == "acme/widgets"
        assert n.branch == "main"
        assert n.cwd == "projects/widgets"
        assert n.worktree is False

    def test_context_fields_default_none(self):
        n = self._make()
        assert n.repo is None
        assert n.branch is None
        assert n.cwd is None
        assert n.worktree is None
