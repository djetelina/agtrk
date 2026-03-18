# agtrk

CLI tool for tracking agent sessions across conversations. SQLite storage, terminal UI, designed for use with Claude Code and similar AI coding agents.

## Install

```bash
pipx install -f git+https://github.com/Phrase-Sandbox/david-jetelina-claude-session-cli.git
```

## Usage

```bash
agtrk                # list active sessions
agtrk show <id>      # session details + notes
agtrk tui            # terminal dashboard (table + kanban views)
agtrk --help         # all commands
```

## CLAUDE.md snippet

Add this to your `CLAUDE.md` (or equivalent agent instructions) to enable session tracking:

```markdown
## Session Tracker

Use the `agtrk` CLI to track work across conversations.

**Every conversation start:**
1. Run `agtrk list` to check for existing work
2. If the user wants to resume something, match it from the list and run `agtrk show <id>` for handoff context
3. If starting new work, run `agtrk register --task "..." [--repo ...] [--status planning]`

**During work:**
- `agtrk update <id> --note "..."` at natural checkpoints (PR opened, phase change, blocker hit)
- `agtrk update <id> --status <planning|implementing|waiting>` when status changes
- `agtrk update <id> --issue PLAT-1234` to associate an issue/ticket
- `agtrk update <id> --repo <repo-name>` to set or change repo association
- Create a heartbeat cron: `CronCreate` with cron `"*/10 * * * *"` and prompt `"Run: agtrk heartbeat <session-id>"`. Store the job ID for cleanup.

**On completion:**
- Delete the heartbeat cron with `CronDelete`
- Run `agtrk complete <id>`

**Corrections:**
- `agtrk reopen <id>` to reactivate a completed session

**Backlog:**
- `agtrk register --task "..." --status todo` for work you notice but shouldn't act on now
```
