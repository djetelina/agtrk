"""CLI commands for claude-sessions."""
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from claude_sessions.db import get_db
from claude_sessions.service import (
    cleanup,
    complete_session,
    get_session,
    heartbeat,
    list_sessions,
    register_session,
    reopen_session,
    update_session,
)

app = typer.Typer(help="Track Claude Code sessions.")
console = Console()


@app.command()
def register(
    task: str = typer.Option(..., "--task", help="Task description"),
    repo: Optional[str] = typer.Option(None, "--repo", help="Repository name"),
    status: str = typer.Option("planning", "--status", help="Initial status"),
    jira: Optional[str] = typer.Option(None, "--jira", help="Jira ticket key"),
    note: Optional[str] = typer.Option(None, "--note", help="Initial note"),
) -> None:
    """Register a new session."""
    conn = get_db()
    try:
        session = register_session(conn, task=task, repo=repo, status=status, jira=jira, note=note)
        console.print(f"Registered session: {session.id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command()
def update(
    id: str = typer.Argument(help="Session ID or prefix"),
    task: Optional[str] = typer.Option(None, "--task", help="New task description"),
    repo: Optional[str] = typer.Option(None, "--repo", help="New repository name"),
    status: Optional[str] = typer.Option(None, "--status", help="New status"),
    jira: Optional[str] = typer.Option(None, "--jira", help="New Jira ticket key"),
    note: Optional[str] = typer.Option(None, "--note", help="Note to append"),
) -> None:
    """Update a session."""
    conn = get_db()
    try:
        update_session(conn, id_or_prefix=id, task=task, repo=repo, status=status, jira=jira, note=note)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


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
        console.print(f"[bold]Repo:[/bold] {session.repo or '-'}")
        console.print(f"[bold]Jira:[/bold] {session.jira or '-'}")
        console.print(f"[bold]Created:[/bold] {session.created_at:%Y-%m-%d %H:%M}")
        console.print(f"[bold]Updated:[/bold] {session.updated_at:%Y-%m-%d %H:%M}")
        if session.completed_at:
            console.print(f"[bold]Completed:[/bold] {session.completed_at:%Y-%m-%d %H:%M}")
        if session.notes:
            console.print("\n[bold]Notes:[/bold]")
            for note in session.notes:
                console.print(f"  {note.created_at:%Y-%m-%d %H:%M}  {note.content}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command(name="list")
def list_cmd(
    archived: bool = typer.Option(False, "--archived", help="Show only archived sessions"),
    show_all: bool = typer.Option(False, "--all", help="Show all sessions including archived"),
) -> None:
    """List sessions."""
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
        table.add_column("Repo")
        table.add_column("Jira")
        table.add_column("Updated")
        for s in sessions:
            table.add_row(
                s.id,
                str(s.status),
                s.task,
                s.repo or "",
                s.jira or "",
                f"{s.updated_at:%Y-%m-%d %H:%M}",
            )
        console.print(table)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command(name="heartbeat")
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


@app.command()
def complete(
    id: str = typer.Argument(help="Session ID or prefix"),
) -> None:
    """Mark a session as done."""
    conn = get_db()
    try:
        complete_session(conn, id_or_prefix=id)
        console.print(f"Completed session: {id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        conn.close()


@app.command()
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
def tui() -> None:
    """Open the TUI dashboard."""
    try:
        from claude_sessions.tui import run_tui
    except ImportError:
        console.print("[red]Error:[/red] TUI requires the 'tui' extra: uv tool install claude-sessions[tui]")
        raise typer.Exit(1)
    run_tui()
