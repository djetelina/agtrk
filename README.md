# agtrk

CLI tool for tracking agent sessions across conversations. SQLite storage, terminal UI, designed for use with Claude Code and similar AI coding agents.

## Install

```bash
pipx install -f git+https://github.com/Phrase-Sandbox/david-jetelina-claude-session-cli.git
agtrk install
```

This installs SessionStart and PreCompact hooks into `~/.claude/settings.json`. The agent receives session context and usage instructions automatically at the start of every conversation and after context compaction.

## Usage

```bash
agtrk                # list active sessions
agtrk show <id>      # session details + notes
agtrk tui            # terminal dashboard (table + kanban views)
agtrk --help         # all commands
```
