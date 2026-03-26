# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-03-26

### Added

- New-version-available notification in TUI — checks PyPI on startup and shows a Textual toast when an upgrade is available

### Changed

- Inject output now places static instructions before the dynamic session table (cache-friendly — stable prefix is cacheable across sessions)

## [1.1.0] - 2026-03-26

### Added

- Project knowledge system — per-repo knowledge entries that agents can store and look up instead of re-exploring the codebase (`learn`, `recall`, `forget`, `update-knowledge`). Inject prompt teaches agents to use it proactively. Gated behind the `knowledge` feature flag (disabled by default).
- Feature flags — DB-backed opt-in for experimental features (`agtrk feature enable/disable/list`)

### Changed

- `register --status todo` no longer auto-detects repo from git origin (todos are often cross-repo observations; use `--repo` to set explicitly)
- Minimum Python version raised from 3.10 to 3.11 (StrEnum requires 3.11+)

## [1.0.0] - 2026-03-24

### Changed

- **Breaking:** Package renamed from `claude-sessions` to `agtrk`
- **Breaking:** Environment variable renamed from `CLAUDE_SESSIONS_DB` to `AGTRK_DB`
- **Breaking:** Database path moved from `~/.local/share/claude-sessions/` to `~/.local/share/agtrk/` (auto-migrated on first run)
- **Breaking:** Minimum `rich` dependency bumped to `~=14.0` (required by textual)
- Lowered Python requirement from 3.12+ to 3.10+
- Runtime dependencies tightened to compatible-release constraints (`~=`)

### Added

- MIT LICENSE file
- Ruff linting and formatting configuration
- Pre-commit hooks (ruff, trailing whitespace, EOF fixer, YAML/TOML checks)
- GitHub Actions CI (ruff, pytest across Python 3.10–3.14, PyPI publish)
- Dependabot for weekly uv dependency updates
- Auto-migration of database from legacy `claude-sessions` path

### Removed

- `.python-version` file (any supported Python version works)

## [0.7.5] - 2026-03-22

### Changed

- Inject prompt now dynamically enumerates valid statuses from the Status enum (includes `waiting`)

## [0.7.4] - 2026-03-22

### Added

- Inject gate exception: agent may ask which todo to resume before completing registration

## [0.7.3] - 2026-03-21

### Added

- Inject prompt now nudges mid-conversation session registration when follow-ups turn into new work

## [0.7.2] - 2026-03-21

### Changed

- Inject register instruction now includes status guidance (todo = noted for later; planning = researching/investigating; implementing = actively writing code)

## [0.7.1] - 2026-03-20

### Added

- TUI detail modal now shows session summary (when set via `agtrk complete --summary`)

### Changed

- Inject register instruction offers `--status <todo|planning|implementing>` instead of hardcoding `implementing`

## [0.7.0] - 2026-03-20

### Added

- `agtrk search <query>` command — case-insensitive search across session tasks and note content
  - `--all` flag to include archived sessions
  - Returns only matching notes per session, not all notes
- Repo and Issue columns in default `list` and `inject` tables (previously only in `list -v`)
- Search command documented in inject instructions

### Changed

- Default table (`list`, `inject`) no longer shows Updated column — available via `list -v`
- Inject gate now requires both session registration AND heartbeat cron before responding
- Cron prompt delimited with markers so agents don't conflate it with surrounding instructions

## [0.6.1] - 2026-03-20

### Fixed

- Status validation — invalid `--status` values now rejected before writing to DB
- Git URL parser — HTTPS URLs with credentials or ports no longer misclassified as SSH
- Removed dead `_is_stale()` function from TUI
- Removed unused imports (`os` in git.py, `subprocess` in test_service.py, `from __future__ import annotations` everywhere)

### Changed

- `open_db()` context manager in `db.py` — shared by CLI and TUI, replaces manual try/finally
- `SessionWithNotes` now composes `Session` instead of duplicating all fields
- `_fetch_session()` helper and `_SESSION_COLUMNS` constant deduplicate service layer queries
- `_resolve_session_id` simplified to single LIKE query
- `_handle_error()` centralizes CLI ValueError handling with `NoReturn` annotation
- `_build_session_table()` shared between `list` and `inject` commands
- Test fixtures consolidated — `git_repo` and `git_repo_with_remote` in conftest.py
- Test helper `_extract_id()` replaces repeated ID parsing boilerplate
- Consistent `X | None` syntax throughout (Python 3.12+)

## [0.6.0] - 2026-03-20

### Added

- `--id` flag on `register` — agents pick a short meaningful slug, random suffix ensures uniqueness
- `--summary` flag on `complete` — optional summary of what was accomplished, shown in `show` output

### Changed

- Session IDs no longer truncated from task description — derived from `--id` or full task with random suffix

## [0.5.0] - 2026-03-20

### Added

- `agtrk delete <id>` command — deletes a session and its notes

### Changed

- Renamed `--jira` flag to `--issue` everywhere (DB migration, model, CLI)
- `agtrk update` now prints confirmation message on success

## [0.4.5] - 2026-03-20

### Changed

- Inject instructions now require user confirmation before marking work completed

## [0.4.4] - 2026-03-20

### Added

- `agtrk uninstall` command — removes hooks and permission from `~/.claude/settings.json` (idempotent)

## [0.4.3] - 2026-03-20

### Fixed

- `install` command no longer grouped under "Agent commands" in help output

## [0.4.2] - 2026-03-20

### Added

- Anti-rationalization table in `agtrk inject` output to catch common evasion patterns
- `agtrk install` now adds `Bash(agtrk:*)` permission so agent commands run without prompting

### Changed

- Reframed inject instructions as a gate on responding rather than a side task

## [0.4.0] - 2026-03-20

### Added

- `agtrk inject` command — outputs session context and usage instructions for agent hooks
- `agtrk install` command — patches `~/.claude/settings.json` with SessionStart + PreCompact hooks (idempotent)

### Changed

- Session tracking instructions no longer need to be in CLAUDE.md — `agtrk inject` is the single source of truth
- Heartbeat cron interval changed from 10 to 30 minutes, now also prompts agent to reflect and add notes
- TUI heartbeat thresholds adjusted: fresh < 35min, warm 35–65min, stale > 65min

## [0.3.1] - 2026-03-19

### Fixed

- TUI refresh no longer blinks or loses card/column focus
- TUI table no longer scrolls horizontally — task text truncated at word boundary with `...`
- TUI table recalculates column widths on terminal resize
- Notes displayed newest-first in both CLI `show` and TUI detail view
- Waiting/done sessions show correct dim dot instead of red heartbeat indicator
- `cwd` only shown on notes when repo is from a remote (path-fallback repos already convey location)

### Changed

- Path-fallback repo display shows `.../parent/name` instead of just `name` for deep paths

## [0.3.0] - 2026-03-19

### Added

- Auto-detect git repo from origin remote on `register` (falls back to path from $HOME)
- Auto-detect git branch, cwd, and worktree status on every note
- `--branch` flag on `update` for overriding auto-detected branch
- Note metadata displayed in `show` command and TUI detail view

### Changed

- Slug IDs shortened from 40 to 20 characters
- Repo displayed as short name (e.g., `widgets` instead of `acme/widgets`)
- `--repo` on `register` is now optional (auto-detected)

## [0.2.0] - 2026-03-18

### Added

- TUI heartbeat breathing animation — fresh heartbeats (within 15min) show a
  smoothly pulsing green dot in kanban view
- Three-tier heartbeat status colors: green (fresh), orange (warm), red (stale)
- Kanban is now the default TUI view
- `--version` / `-V` flag on CLI
- `CLAUDE.md` project conventions and `CHANGELOG.md`

### Changed

- "Jira" column renamed to "Issue" in display (CLI and TUI)

## [0.1.0] - 2026-03-18

### Added

- CLI tool (`agtrk`) for tracking Claude Code sessions
- Commands: `register`, `show`, `list`, `update`, `heartbeat`, `complete`,
  `reopen`, `cleanup`
- SQLite database with WAL mode and automatic migrations
- TUI dashboard with table and kanban views
- Kanban board with keyboard navigation (arrow keys, enter, escape)
- Emoji status indicators and stale session coloring
- Rich-formatted CLI output
- Session notes support
- Repo and issue association
