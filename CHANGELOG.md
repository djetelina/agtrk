# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
