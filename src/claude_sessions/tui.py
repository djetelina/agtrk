"""TUI dashboard for claude-sessions."""

import textwrap
from datetime import datetime, timedelta

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

from claude_sessions.db import get_db
from claude_sessions.models import Status
from claude_sessions.service import get_session, list_sessions

REFRESH_INTERVAL = 30
STALE_THRESHOLD = timedelta(minutes=300)

STATUS_EMOJI = {
    Status.todo: "📋",
    Status.planning: "🧠",
    Status.implementing: "🔨",
    Status.waiting: "⏳",
    Status.done: "✅",
}


def _time_ago(dt: datetime) -> str:
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


class SessionDashboard(App):
    """A TUI dashboard for viewing agent sessions."""

    TITLE = "agtrk"
    CSS = """
    #details {
        height: auto;
        max-height: 50%;
        padding: 1 2;
        background: $surface;
        border-top: solid $primary;
        display: none;
    }
    #details.visible {
        display: block;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "toggle_archived", "Toggle archived"),
        Binding("escape", "close_details", "Close details"),
    ]

    show_archived: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Static(id="details")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "dracula"
        self._load_table()
        self.set_interval(REFRESH_INTERVAL, self._load_table)

    def _load_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_column("ID", max_width=16)
        table.add_column("", max_width=2)
        table.add_column("Task", max_width=35)
        table.add_column("Repo")
        table.add_column("Jira")
        table.add_column("Updated")

        conn = get_db()
        try:
            sessions = list_sessions(conn, include_archived=self.show_archived)
        finally:
            conn.close()

        now = datetime.now()
        for s in sessions:
            if s.status == Status.done:
                style = "dim italic"
            elif s.status != Status.todo and (now - s.updated_at) > STALE_THRESHOLD:
                style = "red"
            else:
                style = ""

            emoji = STATUS_EMOJI.get(s.status, "")

            wrapped_task = "\n".join(textwrap.wrap(s.task, width=35))

            table.add_row(
                Text(s.id, style=style),
                Text(emoji),
                Text(wrapped_task, style=style),
                Text(s.repo or "", style=style),
                Text(s.jira or "", style=style),
                Text(_time_ago(s.updated_at), style=style),
                key=s.id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is None:
            return
        session_id = event.row_key.value
        conn = get_db()
        try:
            session = get_session(conn, session_id)
        finally:
            conn.close()

        emoji = STATUS_EMOJI.get(session.status, "")
        lines = [
            f"[bold]{session.task}[/bold] {emoji} {session.status}",
            f"ID: {session.id}",
            f"Repo: {session.repo or '-'}  |  Jira: {session.jira or '-'}",
            f"Created: {session.created_at:%Y-%m-%d %H:%M}  |  Updated: {_time_ago(session.updated_at)}",
        ]
        if session.completed_at:
            lines.append(f"Completed: {session.completed_at:%Y-%m-%d %H:%M}")
        if session.notes:
            lines.append("")
            lines.append("[bold]Notes:[/bold]")
            for n in session.notes:
                lines.append(f"  {n.created_at:%Y-%m-%d %H:%M}  {n.content}")
        else:
            lines.append("\nNo notes.")

        details = self.query_one("#details", Static)
        details.update("\n".join(lines))
        details.add_class("visible")

    def action_close_details(self) -> None:
        self.query_one("#details", Static).remove_class("visible")

    def action_toggle_archived(self) -> None:
        self.show_archived = not self.show_archived
        self.query_one("#details", Static).remove_class("visible")
        self._load_table()
        state = "on" if self.show_archived else "off"
        self.notify(f"Archived: {state}")


def run_tui() -> None:
    app = SessionDashboard()
    app.run()
