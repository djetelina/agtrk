"""CLI commands for claude-sessions."""

import io
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from claude_sessions.db import get_db
from claude_sessions.git import detect_repo, repo_display_name
from claude_sessions.service import (
    cleanup,
    complete_session,
    delete_session,
    get_session,
    heartbeat,
    list_sessions,
    register_session,
    reopen_session,
    update_session,
)

app = typer.Typer(
    help="Track agent sessions.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        from claude_sessions import __version__

        typer.echo(f"agtrk {__version__}")
        raise typer.Exit


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
    conn = get_db()
    try:
        sessions = list_sessions(conn, include_archived=show_all, archived_only=archived)
        if not sessions:
            if archived:
                console.print("No archived sessions")
            else:
                console.print("No active sessions")
            return
        table = Table()
        table.add_column("ID", style="bold")
        table.add_column("Status")
        table.add_column("Task")
        table.add_column("Updated")
        if verbose:
            table.add_column("Repo")
            table.add_column("Issue")
        for s in sessions:
            row = [
                s.id,
                str(s.status),
                s.task,
                f"{s.updated_at:%Y-%m-%d %H:%M}",
            ]
            if verbose:
                row.extend([repo_display_name(s.repo) if s.repo else "", s.issue or ""])
            table.add_row(*row)
        console.print(table)
    finally:
        conn.close()


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
    conn = get_db()
    try:
        session = get_session(conn, id_or_prefix=id)
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
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command()
def tui() -> None:
    """Open the TUI dashboard."""
    from claude_sessions.tui import run_tui

    run_tui()


@app.command(name="cleanup")
def cleanup_cmd(
    older_than: int = typer.Option(30, "--older-than", help="Delete sessions older than N days"),
) -> None:
    """Delete archived sessions older than a threshold."""
    conn = get_db()
    try:
        count = cleanup(conn, older_than_days=older_than)
        console.print(f"Deleted {count} archived session(s)")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command()
def delete(
    id: str = typer.Argument(help="Session ID or prefix"),
) -> None:
    """Delete a session and its notes."""
    conn = get_db()
    try:
        deleted_id = delete_session(conn, id_or_prefix=id)
        console.print(f"Deleted session: {deleted_id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


INJECT_CRON_PROMPT = """\
Run: `agtrk heartbeat <id>`

Then reflect: since the last note, has there been meaningful progress, a decision, \
a blocker, or a status change? What would help a future session pick up this work? \
If anything comes to mind, run `agtrk update <id> --note "..." --status <status>`.

Also check: does the task description still match what you're doing? Has an issue/ticket \
been created or linked? If so, run `agtrk update <id> --task "..." --issue PLAT-1234`. \
If nothing changed, skip."""

INJECT_INSTRUCTIONS = """\
DO NOT respond to the user until you have done one of the following:
- Resuming existing work: run `agtrk show <id>` and read the notes, then run `agtrk update <id> --status implementing`
- Starting new work: run `agtrk register --task '...' --id <short-slug> --status implementing`

This is a gate on your response, not a side task. You cannot answer, ask clarifying questions, \
read code, or invoke skills until tracking is done.

Then create a heartbeat cron: CronCreate with cron '*/30 * * * *' and the following prompt:

If you catch yourself thinking any of these, stop and register:

| Thought | Reality |
| "Let me just look at the code first" | Register BEFORE touching anything. |
| "This is a quick question" | A weather question becomes trip planning. Register now. |
| "I'll register in a moment" | You won't. Do it now. |
| "User only asked a question" | Questions lead to work. Register first. |
| "I need to understand the task first" | agtrk register accepts updates. Register now, refine later. |

{cron_prompt}

On completion (requires user confirmation — do NOT complete on your own):
- Delete the heartbeat cron with CronDelete
- Run `agtrk complete <id> --summary "Brief description of what was accomplished"`

Corrections:
- `agtrk reopen <id>` to reactivate a completed session

Backlog:
- `agtrk register --task "..." --status todo` for work you notice but shouldn't act on now""".format(
    cron_prompt=INJECT_CRON_PROMPT
)


# --- Agent commands ---


@app.command(rich_help_panel="Agent commands")
def inject() -> None:
    """Output session context and usage instructions for agent hooks."""
    buf = io.StringIO()
    hook_console = Console(file=buf, force_terminal=False, highlight=False)

    conn = get_db()
    try:
        sessions = list_sessions(conn, include_archived=False)
        if sessions:
            table = Table(show_header=True)
            table.add_column("ID", style="bold")
            table.add_column("Status")
            table.add_column("Task")
            table.add_column("Updated")
            for s in sessions:
                table.add_row(s.id, str(s.status), s.task, f"{s.updated_at:%Y-%m-%d %H:%M}")
            hook_console.print("SESSION TRACKER — active work:")
            hook_console.print(table)
        else:
            hook_console.print("SESSION TRACKER — no active sessions.")
    finally:
        conn.close()

    hook_console.print()
    hook_console.print(INJECT_INSTRUCTIONS)
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
        already = any(
            "agtrk inject" in h.get("command", "")
            for entry in entries
            for h in entry.get("hooks", [])
        )
        if not already:
            entries.append(AGTRK_HOOK_ENTRY)

    # Ensure agtrk commands are allowed without prompting
    AGTRK_PERMISSION = "Bash(agtrk:*)"
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    if AGTRK_PERMISSION not in allow:
        allow.append(AGTRK_PERMISSION)

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
            hooks[event] = [
                entry for entry in hooks[event]
                if not any("agtrk inject" in h.get("command", "") for h in entry.get("hooks", []))
            ]

    allow = data.get("permissions", {}).get("allow", [])
    if "Bash(agtrk:*)" in allow:
        allow.remove("Bash(agtrk:*)")

    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    console.print(f"Removed agtrk hooks from {settings_path}")


@app.command(rich_help_panel="Agent commands")
def register(
    task: str = typer.Option(..., "--task", help="Task description"),
    id: Optional[str] = typer.Option(None, "--id", help="Short ID slug (auto-generated if omitted)"),
    repo: Optional[str] = typer.Option(None, "--repo", help="Repository name (auto-detected)"),
    status: str = typer.Option("planning", "--status", help="Initial status"),
    issue: Optional[str] = typer.Option(None, "--issue", help="Issue/ticket key"),
    note: Optional[str] = typer.Option(None, "--note", help="Initial note"),
) -> None:
    """Register a new session."""
    resolved_repo = repo if repo is not None else detect_repo()
    conn = get_db()
    try:
        session = register_session(conn, task=task, slug_id=id, repo=resolved_repo, status=status, issue=issue, note=note)
        console.print(f"Registered session: {session.id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command(rich_help_panel="Agent commands")
def update(
    id: str = typer.Argument(help="Session ID or prefix"),
    task: Optional[str] = typer.Option(None, "--task", help="New task description"),
    repo: Optional[str] = typer.Option(None, "--repo", help="New repository name"),
    status: Optional[str] = typer.Option(None, "--status", help="New status"),
    issue: Optional[str] = typer.Option(None, "--issue", help="Issue/ticket key"),
    note: Optional[str] = typer.Option(None, "--note", help="Note to append"),
    branch: Optional[str] = typer.Option(None, "--branch", help="Branch override for note"),
) -> None:
    """Update a session."""
    conn = get_db()
    try:
        update_session(conn, id_or_prefix=id, task=task, repo=repo, status=status, issue=issue, note=note, branch=branch)
        console.print(f"Updated session: {id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command(name="heartbeat", rich_help_panel="Agent commands")
def heartbeat_cmd(
    id: str = typer.Argument(help="Session ID or prefix"),
) -> None:
    """Bump the updated_at timestamp of a session."""
    conn = get_db()
    try:
        heartbeat(conn, id_or_prefix=id)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command(rich_help_panel="Agent commands")
def complete(
    id: str = typer.Argument(help="Session ID or prefix"),
    summary: Optional[str] = typer.Option(None, "--summary", help="Summary of what was accomplished"),
) -> None:
    """Mark a session as done."""
    conn = get_db()
    try:
        complete_session(conn, id_or_prefix=id, summary=summary)
        console.print(f"Completed session: {id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command(rich_help_panel="Agent commands")
def reopen(
    id: str = typer.Argument(help="Session ID or prefix"),
    status: str = typer.Option("implementing", "--status", help="Status to reopen with"),
) -> None:
    """Reopen a completed session."""
    conn = get_db()
    try:
        reopen_session(conn, id_or_prefix=id, status=status)
        console.print(f"Reopened session: {id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()
