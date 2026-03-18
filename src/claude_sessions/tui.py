"""TUI dashboard for claude-sessions."""

from datetime import datetime, timedelta

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Static

from claude_sessions.db import get_db
from claude_sessions.models import Session, Status
from claude_sessions.service import get_session, list_sessions

REFRESH_INTERVAL = 30
STALE_THRESHOLD = timedelta(minutes=100)

STATUS_EMOJI = {
    Status.todo: "📋",
    Status.planning: "🧠",
    Status.implementing: "🔨",
    Status.waiting: "⏳",
    Status.done: "✅",
}

KANBAN_STATUSES = [Status.todo, Status.planning, Status.implementing, Status.waiting]


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


def _is_stale(s: Session) -> bool:
    return s.status != Status.todo and (datetime.now() - s.updated_at) > STALE_THRESHOLD


def _status_dot(s: Session) -> str:
    if s.status == Status.todo:
        return "[dim]○[/dim]"
    if _is_stale(s):
        return "[red]●[/red]"
    return "[green]●[/green]"


def _group_by_status(sessions: list[Session], include_done: bool = False) -> dict[Status, list[Session]]:
    groups: dict[Status, list[Session]] = {s: [] for s in KANBAN_STATUSES}
    if include_done:
        groups[Status.done] = []
    for s in sessions:
        if s.status in groups:
            groups[s.status].append(s)
    return groups


# ---------------------------------------------------------------------------
# Header (tofuref-style)
# ---------------------------------------------------------------------------

class HeaderStatus(Container):
    DEFAULT_CSS = """
    HeaderStatus {
        layout: horizontal;
        background: $surface;
        width: 1fr;
        height: 3;
        border: round $accent;
        border-right: none;
        border-left: none;
    }
    HeaderStatus > #h-inner {
        layout: grid;
        width: 100%;
        grid-size: 2;
        grid-columns: 1fr auto;
    }
    #h-info {
        width: auto;
        align: left middle;
        layout: horizontal;
        padding: 0 1;
    }
    #h-keys {
        width: auto;
        align: right middle;
        layout: horizontal;
    }
    #h-keys Label {
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._stats_label = Label("")
        self._view_label = Label("table")
        self._archived_label = Label("archived: off")

    def compose(self) -> ComposeResult:
        with Container(id="h-inner"):
            with Container(id="h-info"):
                yield Label("\\[ ")
                yield self._stats_label
                yield Label(" ]  \\[ ")
                yield self._view_label
                yield Label(" ]  \\[ ")
                yield self._archived_label
                yield Label(" ]")
            with Container(id="h-keys"):
                yield Label("[bold]v[/] view")
                yield Label("[bold]a[/] archived")
                yield Label("[bold]q[/] quit")

    def update_status(self, sessions: list, view: str, archived: bool) -> None:
        counts: dict[Status, int] = {}
        for s in sessions:
            counts[s.status] = counts.get(s.status, 0) + 1
        stats = "  ".join(
            f"{STATUS_EMOJI.get(st, '')} {counts.get(st, 0)}"
            for st in KANBAN_STATUSES
        )
        self._stats_label.update(stats)
        self._view_label.update(view)
        self._archived_label.update(f"archived: {'on' if archived else 'off'}")


class HeaderLogo(Static):
    DEFAULT_CSS = """
    HeaderLogo {
        width: auto;
        background: $surface;
    }
    """

    def render(self) -> str:
        # Middle: │  agtrk  │  (visible: 1+2+5+2+1 = 11 chars)
        # Top:   __┌─────┐    (2 spaces + box of 7 = 9, plus ┐ at pos 9)
        # Must match: positions 2-8 are dashes (indices of inner content)
        return (
            "[$accent] ┌─────┐\n"
            "[$secondary]│[/$secondary] [$primary]agtrk[/$primary] [$secondary]│[/$secondary]\n"
            "[$accent] └─────┘"
        )


# ---------------------------------------------------------------------------
# Detail modal
# ---------------------------------------------------------------------------

class DetailScreen(ModalScreen):
    DEFAULT_CSS = """
    DetailScreen { align: center middle; }
    #detail-container {
        width: 80%; height: 80%; background: $surface;
        border: solid $primary; padding: 1 2; overflow-y: auto;
    }
    """
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="detail-container"):
            yield Static(self._content)


def _build_detail_content(session_id: str) -> str:
    conn = get_db()
    try:
        session = get_session(conn, session_id)
    finally:
        conn.close()

    emoji = STATUS_EMOJI.get(session.status, "")
    lines = [
        f"{emoji} [bold]{session.task}[/bold]",
        "",
        f"  [dim]ID[/dim]        {session.id}",
        f"  [dim]Status[/dim]    {session.status}",
        f"  [dim]Repo[/dim]      {session.repo or '-'}",
        f"  [dim]Issue[/dim]     {session.jira or '-'}",
        f"  [dim]Created[/dim]   {_time_ago(session.created_at)}  [dim italic]{session.created_at:%Y-%m-%d %H:%M}[/dim italic]",
        f"  [dim]Heartbeat[/dim] {_time_ago(session.updated_at)}  [dim italic]{session.updated_at:%Y-%m-%d %H:%M}[/dim italic]",
    ]
    if session.completed_at:
        lines.append(f"  [dim]Done[/dim]     {_time_ago(session.completed_at)}  [dim italic]{session.completed_at:%Y-%m-%d %H:%M}[/dim italic]")
    if session.notes:
        lines.append("")
        lines.append("[bold]Notes[/bold]")
        lines.append("")
        for n in session.notes:
            lines.append(f"  [dim]{_time_ago(n.created_at)}[/dim]")
            lines.append(f"  {n.content}")
            lines.append("")
    else:
        lines.append("")
        lines.append("[dim]No notes.[/dim]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Kanban cards
# ---------------------------------------------------------------------------

class CardItem(Static):
    DEFAULT_CSS = """
    CardItem {
        width: 1fr; height: auto; padding: 0 1; margin: 1 0 0 0;
        border-left: vkey $primary-darken-1;
    }
    CardItem:hover { background: $primary-darken-1; }
    CardItem:focus { background: $primary-darken-1; }
    CardItem.stale { color: $error; }
    .card-meta {
        layout: horizontal;
        width: 1fr;
        height: 1;
    }
    .card-meta-left {
        width: 1fr;
        color: $text-muted;
    }
    .card-meta-right {
        width: auto;
        color: $text-muted;
    }
    """
    can_focus = True
    BINDINGS = [
        Binding("up", "prev", show=False),
        Binding("down", "next", show=False),
        Binding("left", "left_card", show=False),
        Binding("right", "right_card", show=False),
    ]

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session

    def _find_adjacent_column_card(self, direction: int) -> None:
        """Jump to the card at a similar Y position in the nearest non-empty column."""
        my_col = next(a for a in self.ancestors_with_self if isinstance(a, CardColumn))
        all_cols = list(self.app.query(CardColumn))
        idx = all_cols.index(my_col)
        my_y = self.region.y
        i = idx + direction
        while 0 <= i < len(all_cols):
            cards = list(all_cols[i].query(CardItem))
            if cards:
                # Find the card closest to our Y position
                best = min(cards, key=lambda c: abs(c.region.y - my_y))
                best.focus()
                return
            i += direction
        target = idx + direction
        if 0 <= target < len(all_cols):
            all_cols[target].focus()

    def action_left_card(self) -> None:
        self._find_adjacent_column_card(-1)

    def action_right_card(self) -> None:
        self._find_adjacent_column_card(1)

    def compose(self) -> ComposeResult:
        s = self.session
        task = s.task[:40] + "…" if len(s.task) > 40 else s.task
        yield Static(f"[bold]{task}[/bold]")
        repo = s.repo or ""
        with Horizontal(classes="card-meta"):
            yield Static(repo, classes="card-meta-left")
            yield Static(_status_dot(s), classes="card-meta-right")

    def on_click(self) -> None:
        self.app.push_screen(DetailScreen(_build_detail_content(self.session.id)))

    def key_enter(self) -> None:
        self.app.push_screen(DetailScreen(_build_detail_content(self.session.id)))

    def action_prev(self) -> None:
        siblings = list(self.parent.query(CardItem))
        idx = siblings.index(self)
        if idx > 0:
            siblings[idx - 1].focus()

    def action_next(self) -> None:
        siblings = list(self.parent.query(CardItem))
        idx = siblings.index(self)
        if idx < len(siblings) - 1:
            siblings[idx + 1].focus()


class CardColumn(VerticalScroll):
    DEFAULT_CSS = """
    CardColumn {
        width: 1fr; height: 1fr; margin: 0;
        scrollbar-size: 0 0;
    }
    CardColumn:focus .col-header { background: $accent; color: auto; }
    .col-header { width: 1fr; height: 1; text-align: center; text-style: bold; background: $primary-darken-2; margin: 0 0 1 0; border-left: vkey $accent; }
    CardColumn.first-col .col-header { border-left: none; }
    """
    can_focus = True
    BINDINGS = [
        Binding("enter", "enter_col", show=False),
        Binding("left", "prev_col", show=False),
        Binding("right", "next_col", show=False),
    ]

    def __init__(self, status: Status) -> None:
        super().__init__()
        self.status = status

    def compose(self) -> ComposeResult:
        emoji = STATUS_EMOJI.get(self.status, "")
        yield Static(f"{emoji} {self.status.value}", classes="col-header")

    def action_enter_col(self) -> None:
        cards = list(self.query(CardItem))
        if cards:
            cards[0].focus()

    def action_prev_col(self) -> None:
        cols = list(self.app.query(CardColumn))
        idx = cols.index(self)
        if idx > 0:
            cols[idx - 1].focus()

    def action_next_col(self) -> None:
        cols = list(self.app.query(CardColumn))
        idx = cols.index(self)
        if idx < len(cols) - 1:
            cols[idx + 1].focus()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class SessionDashboard(App):
    TITLE = "agtrk"
    CSS = """
    #header { dock: top; height: 3; layout: horizontal; }
    #table-view { height: 1fr; }
    #board { width: 1fr; height: 1fr; display: none; }
    #board.visible { display: block; }
    #table-view.hidden { display: none; }
    """

    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("a", "toggle_archived", show=False),
        Binding("v", "toggle_view", show=False),
        Binding("escape", "go_back", show=False),
    ]

    show_archived: reactive[bool] = reactive(False)
    kanban_view: bool = False
    _sessions: list[Session] = []

    def compose(self) -> ComposeResult:
        with Container(id="header"):
            yield HeaderStatus()
            yield HeaderLogo()
        yield DataTable(id="table-view", cursor_type="row", zebra_stripes=True)
        yield Horizontal(id="board")

    def on_mount(self) -> None:
        self.theme = "dracula"
        self._load_data()
        self.set_interval(REFRESH_INTERVAL, self._load_data)

    def _refresh_header(self) -> None:
        view = "kanban" if self.kanban_view else "table"
        self.query_one(HeaderStatus).update_status(
            self._sessions, view, self.show_archived
        )

    def _load_data(self) -> None:
        conn = get_db()
        try:
            self._sessions = list_sessions(conn, include_archived=self.show_archived)
        finally:
            conn.close()
        self._load_table()
        self._load_board()
        self._refresh_header()

    def _load_table(self) -> None:
        table = self.query_one("#table-view", DataTable)
        table.clear(columns=True)
        # Fixed columns: dot(1) + ID(16) + emoji(2) + Repo(16) + Jira(10) + borders/padding(~10) = ~55
        term_width = self.size.width
        task_width = max(20, term_width - 55)

        table.add_column("", width=1)
        table.add_column("ID", width=16)
        table.add_column("", width=2)
        table.add_column("Task", width=task_width)
        table.add_column("Repo", width=16)
        table.add_column("Issue", width=10)

        for s in self._sessions:
            if s.status == Status.done:
                style = "dim italic"
            else:
                style = ""
            emoji = STATUS_EMOJI.get(s.status, "")
            task = s.task[:task_width] + "…" if len(s.task) > task_width else s.task
            table.add_row(
                Text.from_markup(_status_dot(s)),
                Text(s.id, style=style),
                Text(emoji),
                Text(task, style=style),
                Text(s.repo or "", style=style),
                Text(s.jira or "", style=style),
                key=s.id,
            )

    def _load_board(self) -> None:
        board = self.query_one("#board", Horizontal)
        board.remove_children()
        groups = _group_by_status(self._sessions, self.show_archived)
        first = True
        for status, items in groups.items():
            col = CardColumn(status)
            if first:
                col.add_class("first-col")
                first = False
            board.mount(col)
            for s in items:
                col.mount(CardItem(s))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is None:
            return
        self.push_screen(DetailScreen(_build_detail_content(event.row_key.value)))

    def action_go_back(self) -> None:
        if self.kanban_view:
            focused = self.focused
            if isinstance(focused, CardItem):
                for a in focused.ancestors_with_self:
                    if isinstance(a, CardColumn):
                        a.focus()
                        return

    def action_toggle_archived(self) -> None:
        self.show_archived = not self.show_archived
        self._load_data()

    def action_toggle_view(self) -> None:
        self.kanban_view = not self.kanban_view
        self.query_one("#table-view").toggle_class("hidden")
        self.query_one("#board").toggle_class("visible")
        if self.kanban_view:
            cols = list(self.query(CardColumn))
            if cols:
                cols[0].focus()
        else:
            self.query_one("#table-view", DataTable).focus()
        self._refresh_header()


def run_tui() -> None:
    app = SessionDashboard()
    app.run()
