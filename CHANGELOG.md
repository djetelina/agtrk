# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
