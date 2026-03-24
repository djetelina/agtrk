# CLAUDE.md

## Project

`agtrk` — CLI + TUI for tracking agent sessions across conversations.

## Stack

- Python 3.11+, managed with `uv`
- CLI: Typer + Rich
- TUI: Textual
- DB: SQLite (WAL mode)
- Tests: pytest

## Conventions

- Changelog: `CHANGELOG.md` — [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Update the `[Unreleased]` section when adding/changing/fixing features.
- Tests live in `tests/` and use a temporary DB via the `db` fixture in `conftest.py`.
- Linting/formatting: Ruff (config in `pyproject.toml`, pre-commit hooks in `.pre-commit-config.yaml`).
- Source layout: `src/agtrk/` — models, db, service, cli, tui.

## Releasing

Version bump + changelog only for app changes (code, prompts, features). Not for docs, tests, or config-only changes.

When releasing:

1. Bump the version in `pyproject.toml` (single source of truth — `__version__` is derived via `importlib.metadata`).
2. Move `[Unreleased]` entries in `CHANGELOG.md` into a new `[X.Y.Z] - YYYY-MM-DD` section.
3. Commit the version bump + changelog as its own commit (e.g., `release: vX.Y.Z`).

## Prompt Decision Records

Prompt engineering decisions are documented in `docs/prompt-decisions/`. Each file covers one decision with sections: Context, Decision, Tradeoff, Expectation. Keep them brief — the goal is to track why prompt changes were made and what to watch for.
