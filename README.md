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

**Every conversation start (MANDATORY — do this before any implementation work):**
1. Run `agtrk list` to check for existing work
2. If resuming existing work: run `agtrk show <id>` and **STOP — read the notes**. Notes contain blockers, decisions, and pending actions from prior sessions. Do not start implementation until you understand the current state. Then run `agtrk update <id> --status implementing`.
3. If starting new work: run `agtrk register --task "..." [--status implementing]` **immediately**. Do not defer registration — if you're doing work, it must be tracked. Repo is auto-detected from git origin.
4. Create a heartbeat cron: `CronCreate` with cron `"*/10 * * * *"` and prompt `"Run: agtrk heartbeat <session-id>"`. Store the job ID for cleanup.

**During work:**
- `agtrk update <id> --note "..."` at natural checkpoints (each apply, config decision, phase change, blocker hit) — do this proactively, not only when asked
- `agtrk update <id> --status <planning|implementing|waiting>` when status changes
- `agtrk update <id> --task "..."` to update the task description
- `agtrk update <id> --issue PLAT-1234` to associate an issue/ticket
- `agtrk update <id> --repo <repo-name>` to override auto-detected repo

**On completion:**
- Delete the heartbeat cron with `CronDelete`
- Run `agtrk complete <id>`

**Corrections:**
- `agtrk reopen <id>` to reactivate a completed session

**Backlog:**
- `agtrk register --task "..." --status todo` for work you notice but shouldn't act on now
```
