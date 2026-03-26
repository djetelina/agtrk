# agtrk

Continuity for Claude Code conversations.

Claude Code sessions are ephemeral — close one, and the next has no idea what you were doing. agtrk fixes that. It hooks into Claude Code and gives the agent a persistent view of what's in progress, so conversations can pick up where the last one left off.

> This project is built almost entirely with Claude Code.

## How it works

`agtrk install` adds hooks to your Claude Code settings. At the start of every conversation, agtrk injects a table of active sessions and instructions for the agent. The agent then registers what it's working on, leaves notes, and updates status — all stored in a local SQLite database. The next conversation sees all of it.

There's also a TUI dashboard (`agtrk tui`) if you want to see everything at a glance.

## Install

```bash
pipx install agtrk
agtrk install
```

## Commands

```bash
agtrk                         # list active sessions
agtrk show <id>               # session details + notes
agtrk tui                     # terminal dashboard (table + kanban views)
agtrk list                    # list with filters (--archived, --all, --verbose)
agtrk search <query>          # search sessions by task/note content
agtrk delete <id>             # delete a session and its notes
agtrk install                 # add hooks to ~/.claude/settings.json
agtrk uninstall               # remove hooks
agtrk cleanup                 # delete archived sessions older than 30 days
agtrk feature list            # show feature flags and their status
agtrk feature enable <name>   # enable a feature
agtrk feature disable <name>  # disable a feature
agtrk --help                  # all commands
```

## Feature flags

Some features are gated behind flags and disabled by default. Enable them with `agtrk feature enable <name>`.

| Feature | Description |
|---------|-------------|
| `knowledge` | Per-repo project knowledge that agents can store and look up instead of re-exploring the codebase. Adds `learn`, `recall`, `forget`, and `update-knowledge` commands, and teaches the inject prompt to use them. |

## License

MIT
