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
agtrk list           # list with filters (--archived, --all, --verbose)
agtrk delete <id>    # delete a session and its notes
agtrk install        # add hooks to ~/.claude/settings.json
agtrk uninstall      # remove hooks from ~/.claude/settings.json
agtrk cleanup        # delete archived sessions older than 30 days
agtrk --help         # all commands
```
