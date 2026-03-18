# CLAUDE.md

## Project

`claude-sessions` (`agtrk`) — CLI + TUI for tracking Claude Code work sessions.

## Stack

- Python 3.12+, managed with `uv`
- CLI: Typer + Rich
- TUI: Textual
- DB: SQLite (WAL mode)
- Tests: pytest

## Conventions

- Changelog: `CHANGELOG.md` — [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Update the `[Unreleased]` section when adding/changing/fixing features.
- Tests live in `tests/` and use a temporary DB via the `db_conn` fixture in `conftest.py`.
- Source layout: `src/claude_sessions/` — models, db, service, cli, tui.

## Releasing

Every `git push` is a version release. Before pushing:

1. Bump the version in `pyproject.toml` (single source of truth — `__version__` is derived via `importlib.metadata`).
2. Move `[Unreleased]` entries in `CHANGELOG.md` into a new `[X.Y.Z] - YYYY-MM-DD` section.
3. Commit the version bump + changelog as its own commit (e.g., `release: vX.Y.Z`).
