"""CLI commands for agtrk."""

import io
import json
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from agtrk.db import open_db
from agtrk.git import detect_repo, repo_display_name
from agtrk.models import Feature, Kind, Status
from agtrk.service import (
    cleanup,
    complete_session,
    delete_session,
    forget,
    get_knowledge,
    get_session,
    heartbeat,
    is_feature_enabled,
    learn,
    list_features,
    list_sessions,
    recall,
    register_session,
    reopen_session,
    search_sessions,
    set_feature,
    update_knowledge,
    update_session,
)

app = typer.Typer(
    help="Maintain continuity across Claude Code conversations.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)
console = Console()


def _handle_error(e: ValueError) -> NoReturn:
    console.print(f"[red]Error:[/red] {e}")
    raise typer.Exit(1)


def _require_repo(repo: str | None) -> str:
    """Resolve repo, raising Exit(1) if undetectable."""
    resolved = repo if repo is not None else detect_repo()
    if resolved is None:
        console.print("[red]Error:[/red] Could not detect repo from git remote. Use --repo org/name (e.g. --repo acme/widgets).")
        raise typer.Exit(1)
    return resolved


def _version_callback(value: bool) -> None:
    if value:
        from agtrk import __version__

        typer.echo(f"agtrk {__version__}")
        raise typer.Exit


def _build_session_table(sessions: list) -> Table:
    """Build a Rich table of sessions (shared by list and inject)."""
    table = Table(show_header=True)
    table.add_column("ID", style="bold")
    table.add_column("Status")
    table.add_column("Task")
    table.add_column("Repo")
    table.add_column("Issue")
    for s in sessions:
        table.add_row(
            s.id,
            str(s.status),
            s.task,
            repo_display_name(s.repo) if s.repo else "",
            s.issue or "",
        )
    return table


@app.callback()
def default(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    """Show active sessions if no command is given."""
    if ctx.invoked_subcommand is not None:
        return
    _print_list(archived=False, show_all=False)


def _print_list(archived: bool, show_all: bool, verbose: bool = False) -> None:
    with open_db() as conn:
        sessions = list_sessions(conn, include_archived=show_all, archived_only=archived)
    if not sessions:
        console.print("No archived sessions" if archived else "No active sessions")
        return
    if verbose:
        table = Table(show_header=True)
        table.add_column("ID", style="bold")
        table.add_column("Status")
        table.add_column("Task")
        table.add_column("Repo")
        table.add_column("Issue")
        table.add_column("Updated")
        for s in sessions:
            table.add_row(
                s.id,
                str(s.status),
                s.task,
                repo_display_name(s.repo) if s.repo else "",
                s.issue or "",
                f"{s.updated_at:%Y-%m-%d %H:%M}",
            )
    else:
        table = _build_session_table(sessions)
    console.print(table)


# --- User commands ---


@app.command(name="list")
def list_cmd(
    archived: bool = typer.Option(False, "--archived", help="Show only archived sessions"),
    show_all: bool = typer.Option(False, "--all", help="Show all sessions including archived"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all columns"),
) -> None:
    """List sessions."""
    _print_list(archived=archived, show_all=show_all, verbose=verbose)


@app.command()
def show(
    id: str = typer.Argument(help="Session ID or prefix"),
) -> None:
    """Show details of a session."""
    try:
        with open_db() as conn:
            session = get_session(conn, id_or_prefix=id)
    except ValueError as e:
        _handle_error(e)

    console.print(f"[bold]Task:[/bold] {session.task}")
    console.print(f"[bold]Status:[/bold] {session.status}")
    console.print(f"[bold]Repo:[/bold] {repo_display_name(session.repo) if session.repo else '-'}")
    console.print(f"[bold]Issue:[/bold] {session.issue or '-'}")
    console.print(f"[bold]Created:[/bold] {session.created_at:%Y-%m-%d %H:%M}")
    console.print(f"[bold]Updated:[/bold] {session.updated_at:%Y-%m-%d %H:%M}")
    if session.completed_at:
        console.print(f"[bold]Completed:[/bold] {session.completed_at:%Y-%m-%d %H:%M}")
    if session.summary:
        console.print(f"\n[bold]Summary:[/bold] {session.summary}")
    if session.notes:
        console.print("\n[bold]Notes:[/bold]")
        for note in reversed(session.notes):
            parts = [f"{note.created_at:%Y-%m-%d %H:%M}"]
            tag_parts = []
            if note.repo:
                tag_parts.append(repo_display_name(note.repo))
            if note.branch:
                tag_parts.append(f"@{note.branch}")
            if tag_parts:
                parts.append(f"[{''.join(tag_parts)}]")
            if note.worktree:
                parts.append("\U0001f333")
            console.print(f"  {' '.join(parts)}")
            console.print(f"  {note.content}")


@app.command()
def search(
    query: str = typer.Argument(help="Search term"),
    all_sessions: bool = typer.Option(False, "--all", help="Include archived sessions"),
) -> None:
    """Search across session tasks and notes."""
    with open_db() as conn:
        results = search_sessions(conn, query, include_archived=all_sessions)
    if not results:
        console.print(f"No matches for '{query}'")
        return
    for swn in results:
        task_match = query.lower() in swn.task.lower()
        status_str = f"[dim]{swn.status}[/dim]"
        console.print(f"[bold]{swn.id}[/bold] {status_str} — {swn.task}")
        if task_match and not swn.notes:
            console.print("  [dim](task match)[/dim]")
        for note in swn.notes:
            console.print(f"  {note.created_at:%Y-%m-%d %H:%M} {note.content}")
        console.print()


@app.command()
def tui() -> None:
    """Open the TUI dashboard."""
    from agtrk.tui import run_tui

    run_tui()


@app.command(name="cleanup")
def cleanup_cmd(
    older_than: int = typer.Option(30, "--older-than", help="Delete sessions older than N days"),
) -> None:
    """Delete archived sessions older than a threshold."""
    try:
        with open_db() as conn:
            count = cleanup(conn, older_than_days=older_than)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Deleted {count} archived session(s)")


@app.command()
def delete(
    id: str = typer.Argument(help="Session ID or prefix"),
) -> None:
    """Delete a session and its notes."""
    try:
        with open_db() as conn:
            deleted_id = delete_session(conn, id_or_prefix=id)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Deleted session: {deleted_id}")


INJECT_CRON_PROMPT = """\
Run: `agtrk heartbeat <id>`

Then reflect: since the last note, has there been meaningful progress, a decision, \
a blocker, or a status change? What would help a future session pick up this work? \
If anything comes to mind, run `agtrk update <id> --note "..." --status <status>`.

Also check: does the task description still match what you're doing? Has an issue/ticket \
been created or linked? If so, run `agtrk update <id> --task "..." --issue PROJ-1234`. \
If nothing changed, skip."""

INJECT_INSTRUCTIONS_BASE = """\
DO NOT respond to the user until you have done ALL of the following:
1. Register or resume:
   - Resuming existing work: run `agtrk show <id>` and read the notes, then run `agtrk update <id> --status implementing`
   - Starting new work: run `agtrk register --task '...' --id <short-slug> \
--status <{statuses}>`
     (todo = noted for later; planning = researching/investigating; implementing = actively writing code; \
waiting = blocked or awaiting external input)
2. Create a heartbeat cron: CronCreate with cron '*/30 * * * *' and the prompt between the markers:

--- BEGIN CRON PROMPT ---
{cron_prompt}
--- END CRON PROMPT ---

This is a gate on your response, not a side task. You cannot answer, ask clarifying questions, \
read code, or invoke skills until both steps are done.

Exception — choosing a todo: if the user's message signals they want to pick up existing \
todo work (e.g. "let me work on a todo", "what's on my backlog", "pick up where I left off"), \
you may ask which session they want to resume BEFORE completing step 1. Once they choose, \
use the "Resuming existing work" path with that session's ID.

If you catch yourself thinking any of these, stop and register:

| Thought | Reality |
| "Let me just look at the code first" | Register BEFORE touching anything. |
| "This is a quick question" | A weather question becomes trip planning. Register now. |
| "I'll register in a moment" | You won't. Do it now. |
| "User only asked a question" | Questions lead to work. Register first. |
| "I need to understand the task first" | agtrk register accepts updates. Register now, refine later. |

If you completed a session mid-conversation and a follow-up turns into new work \
(code changes, investigations, or anything beyond a simple answer), register a new session before proceeding.

On completion (requires user confirmation — do NOT complete on your own):
- Delete the heartbeat cron with CronDelete
- Run `agtrk complete <id> --summary "Brief description of what was accomplished"`

Corrections:
- `agtrk reopen <id>` to reactivate a completed session

Search:
- `agtrk search <query>` to find sessions by task or note content (case-insensitive)
- `agtrk search <query> --all` to include archived sessions

Backlog:
- `agtrk register --task "..." --status todo` for work you notice but shouldn't act on now""".format(
    cron_prompt=INJECT_CRON_PROMPT,
    statuses="|".join(s.value for s in Status if s != Status.done),
)


INJECT_INSTRUCTIONS_KNOWLEDGE = """

Project knowledge (auto-scoped to current repo — NOT the same as auto-memory; \
auto-memory rules about "don't save project structure" do NOT apply here):
- When you need codebase context, `agtrk recall --search <topic>` FIRST. \
If it returns results and you are not about to edit code, you have enough context — move on. \
Only read files when recall returns nothing or you need line-level detail for edits.
- List all entries for this repo: `agtrk recall`
- After learning stable project facts, you MUST save them via \
`agtrk learn --kind <kind> --title "..." "..."` BEFORE responding to the user. \
This especially applies when Explore subagents return results — review their findings \
for stable, reusable facts and save each one. Treat this like the register/cron gate.
- Keep entries focused — one topic per entry so search stays useful.
  Bad:  "Project uses Typer, tests in tests/, DB uses WAL mode, service layer owns SQL"
  Good: 4 separate entries — "CLI framework: Typer + Rich", "test structure", \
  "DB conventions: WAL + migrations", "service layer pattern".
- If you discover a knowledge entry is outdated, update it immediately:
  `agtrk update-knowledge <id> "corrected content"`
- If an entry is no longer relevant, remove it: `agtrk forget <id>`
- Do NOT learn things already documented in CLAUDE.md — knowledge entries are for \
facts discovered during work, not duplicates of existing project docs.


Knowledge kinds:
  {kinds}""".format(
    kinds="\n  ".join(f"{k.value:14s} — {k.description}" for k in Kind),
)


# --- Agent commands ---


@app.command(rich_help_panel="Agent commands")
def inject() -> None:
    """Output session context and usage instructions for agent hooks."""
    buf = io.StringIO()
    hook_console = Console(file=buf, force_terminal=False, highlight=False)

    with open_db() as conn:
        sessions = list_sessions(conn, include_archived=False)
        knowledge_enabled = is_feature_enabled(conn, Feature.knowledge)

    instructions = INJECT_INSTRUCTIONS_BASE
    if knowledge_enabled:
        instructions += INJECT_INSTRUCTIONS_KNOWLEDGE
    hook_console.print(instructions)

    hook_console.print()
    if sessions:
        hook_console.print("SESSION TRACKER — active work:")
        hook_console.print(_build_session_table(sessions))
    else:
        hook_console.print("SESSION TRACKER — no active sessions.")
    typer.echo(buf.getvalue(), nl=False)


AGTRK_HOOK_ENTRY = {
    "hooks": [
        {
            "type": "command",
            "command": "agtrk inject",
            "timeout": 10,
            "statusMessage": "Loading session tracker...",
        }
    ]
}


@app.command()
def install(
    settings: str = typer.Option(
        str(Path.home() / ".claude" / "settings.json"),
        "--settings",
        help="Path to Claude Code settings.json",
    ),
) -> None:
    """Install agtrk hooks into Claude Code settings."""
    settings_path = Path(settings)

    if settings_path.exists():
        data = json.loads(settings_path.read_text())
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    hooks = data.setdefault("hooks", {})

    for event in ("SessionStart", "PreCompact"):
        entries = hooks.setdefault(event, [])
        already = any("agtrk inject" in h.get("command", "") for entry in entries for h in entry.get("hooks", []))
        if not already:
            entries.append(AGTRK_HOOK_ENTRY)

    # Ensure agtrk commands are allowed without prompting
    agtrk_permission = "Bash(agtrk:*)"
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    if agtrk_permission not in allow:
        allow.append(agtrk_permission)

    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    console.print(f"Installed agtrk hooks into {settings_path}")


@app.command()
def uninstall(
    settings: str = typer.Option(
        str(Path.home() / ".claude" / "settings.json"),
        "--settings",
        help="Path to Claude Code settings.json",
    ),
) -> None:
    """Remove agtrk hooks from Claude Code settings."""
    settings_path = Path(settings)

    if not settings_path.exists():
        console.print("Nothing to uninstall — settings file not found.")
        return

    data = json.loads(settings_path.read_text())

    hooks = data.get("hooks", {})
    for event in ("SessionStart", "PreCompact"):
        if event in hooks:
            hooks[event] = [entry for entry in hooks[event] if not any("agtrk inject" in h.get("command", "") for h in entry.get("hooks", []))]

    allow = data.get("permissions", {}).get("allow", [])
    if "Bash(agtrk:*)" in allow:
        allow.remove("Bash(agtrk:*)")

    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    console.print(f"Removed agtrk hooks from {settings_path}")


@app.command(rich_help_panel="Agent commands")
def register(
    task: str = typer.Option(..., "--task", help="Task description"),
    id: str | None = typer.Option(None, "--id", help="Short ID slug (auto-generated if omitted)"),
    repo: str | None = typer.Option(None, "--repo", help="Repository name (auto-detected)"),
    status: str = typer.Option("planning", "--status", help="Initial status"),
    issue: str | None = typer.Option(None, "--issue", help="Issue/ticket key"),
    note: str | None = typer.Option(None, "--note", help="Initial note"),
) -> None:
    """Register a new session."""
    resolved_repo = repo if repo is not None else (None if status == "todo" else detect_repo())
    try:
        with open_db() as conn:
            session = register_session(conn, task=task, slug_id=id, repo=resolved_repo, status=status, issue=issue, note=note)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Registered session: {session.id}")


@app.command(rich_help_panel="Agent commands")
def update(
    id: str = typer.Argument(help="Session ID or prefix"),
    task: str | None = typer.Option(None, "--task", help="New task description"),
    repo: str | None = typer.Option(None, "--repo", help="New repository name"),
    status: str | None = typer.Option(None, "--status", help="New status"),
    issue: str | None = typer.Option(None, "--issue", help="Issue/ticket key"),
    note: str | None = typer.Option(None, "--note", help="Note to append"),
    branch: str | None = typer.Option(None, "--branch", help="Branch override for note"),
) -> None:
    """Update a session."""
    try:
        with open_db() as conn:
            update_session(conn, id_or_prefix=id, task=task, repo=repo, status=status, issue=issue, note=note, branch=branch)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Updated session: {id}")


@app.command(name="heartbeat", rich_help_panel="Agent commands")
def heartbeat_cmd(
    id: str = typer.Argument(help="Session ID or prefix"),
) -> None:
    """Bump the updated_at timestamp of a session."""
    try:
        with open_db() as conn:
            heartbeat(conn, id_or_prefix=id)
    except ValueError as e:
        _handle_error(e)


@app.command(rich_help_panel="Agent commands")
def complete(
    id: str = typer.Argument(help="Session ID or prefix"),
    summary: str | None = typer.Option(None, "--summary", help="Summary of what was accomplished"),
) -> None:
    """Mark a session as done."""
    try:
        with open_db() as conn:
            complete_session(conn, id_or_prefix=id, summary=summary)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Completed session: {id}")


@app.command(rich_help_panel="Agent commands")
def reopen(
    id: str = typer.Argument(help="Session ID or prefix"),
    status: str = typer.Option("implementing", "--status", help="Status to reopen with"),
) -> None:
    """Reopen a completed session."""
    try:
        with open_db() as conn:
            reopen_session(conn, id_or_prefix=id, status=status)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Reopened session: {id}")


# --- Knowledge commands ---


@app.command(name="learn", rich_help_panel="Agent commands")
def learn_cmd(
    content: str = typer.Argument(help="Knowledge content"),
    kind: str = typer.Option(..., "--kind", help=f"Knowledge kind ({', '.join(k.value for k in Kind)})"),
    title: str = typer.Option(..., "--title", help="Short searchable title"),
    repo: str | None = typer.Option(None, "--repo", help="Repository name (auto-detected)"),
) -> None:
    """Store a project knowledge entry."""
    resolved_repo = _require_repo(repo)
    try:
        with open_db() as conn:
            entry = learn(conn, repo=resolved_repo, kind=kind, title=title, content=content)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Learned #{entry.id}: {entry.title}")


def _print_knowledge_entry(entry, show_content: bool = False) -> None:
    """Print a single knowledge entry."""
    console.print(f"[bold]#{entry.id}[/bold] \\[{entry.kind}] {entry.title}")
    if show_content:
        console.print(f"  {entry.content}")


@app.command(name="recall", rich_help_panel="Agent commands")
def recall_cmd(
    ids: list[int] = typer.Argument(None, help="Knowledge entry IDs (shows full detail)"),
    kind: str | None = typer.Option(None, "--kind", help=f"Filter by kind ({', '.join(k.value for k in Kind)})"),
    search: str | None = typer.Option(None, "--search", help="Keyword search in title/content"),
    repo: str | None = typer.Option(None, "--repo", help="Repository name (auto-detected)"),
) -> None:
    """Look up project knowledge."""
    with open_db() as conn:
        if ids:
            for entry_id in ids:
                try:
                    entry = get_knowledge(conn, knowledge_id=entry_id)
                except ValueError as e:
                    _handle_error(e)
                _print_knowledge_entry(entry, show_content=True)
            return
        resolved_repo = _require_repo(repo)
        try:
            entries = recall(conn, repo=resolved_repo, kind=kind, search=search)
        except ValueError as e:
            _handle_error(e)
    if not entries:
        console.print("No knowledge entries found.")
        return
    for entry in entries:
        _print_knowledge_entry(entry, show_content=bool(search))
    if not search:
        console.print(f"\n[dim]Detail: agtrk recall <id> [<id> ...][/dim]")


@app.command(name="forget", rich_help_panel="Agent commands")
def forget_cmd(
    id: int = typer.Argument(help="Knowledge entry ID"),
) -> None:
    """Delete a knowledge entry."""
    try:
        with open_db() as conn:
            forget(conn, knowledge_id=id)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Forgot knowledge entry #{id}")


@app.command(name="update-knowledge", rich_help_panel="Agent commands")
def update_knowledge_cmd(
    id: int = typer.Argument(help="Knowledge entry ID"),
    content: str | None = typer.Argument(None, help="New content"),
    title: str | None = typer.Option(None, "--title", help="New title"),
    kind: str | None = typer.Option(None, "--kind", help="New kind"),
) -> None:
    """Update a knowledge entry."""
    try:
        with open_db() as conn:
            entry = update_knowledge(conn, knowledge_id=id, title=title, content=content, kind=kind)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Updated knowledge entry #{entry.id}: {entry.title}")


# --- Feature flag commands ---

feature_app = typer.Typer(help="Manage feature flags.", rich_markup_mode="rich")
app.add_typer(feature_app, name="feature")


@feature_app.command(name="enable")
def feature_enable_cmd(
    name: str = typer.Argument(help="Feature name"),
) -> None:
    """Enable a feature flag."""
    try:
        with open_db() as conn:
            set_feature(conn, name, enabled=True)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Enabled feature: {name}")


@feature_app.command(name="disable")
def feature_disable_cmd(
    name: str = typer.Argument(help="Feature name"),
) -> None:
    """Disable a feature flag."""
    try:
        with open_db() as conn:
            set_feature(conn, name, enabled=False)
    except ValueError as e:
        _handle_error(e)
    console.print(f"Disabled feature: {name}")


@feature_app.command(name="list")
def feature_list_cmd() -> None:
    """List all feature flags and their status."""
    with open_db() as conn:
        features = list_features(conn)
    table = Table(show_header=True)
    table.add_column("Feature", style="bold")
    table.add_column("Status")
    for feat, enabled in features:
        status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
        table.add_row(feat.value, status)
    console.print(table)
