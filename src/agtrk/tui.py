"""TUI dashboard for agtrk."""

import math
from datetime import datetime, timedelta

from packaging.version import Version
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Label, Link, Static

from agtrk import __version__
from agtrk.db import open_db
from agtrk.git import repo_display_name
from agtrk.models import Session, Status
from agtrk.service import get_session, list_knowledge_repos, list_sessions
from agtrk.tui_knowledge import RepoDetailView, RepoGrid, RepoTile
from agtrk.version_check import get_latest_pypi_version

REFRESH_INTERVAL = 30
FRESH_THRESHOLD = timedelta(minutes=35)
STALE_THRESHOLD = timedelta(minutes=65)

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


def _truncate(text: str, width: int) -> str:
    """Truncate text to width, breaking at word boundary, appending '...' if cut."""
    if len(text) <= width:
        return text
    cut = width - 3  # room for "..."
    if cut <= 0:
        return text[:width]
    # Find last space before the cut point
    space = text.rfind(" ", 0, cut + 1)
    if space > 0:
        return text[:space] + "..."
    return text[:cut] + "..."


def _heartbeat_tier(s: Session) -> str:
    """Return 'todo', 'fresh', 'warm', or 'stale' based on heartbeat age."""
    if s.status in (Status.todo, Status.waiting, Status.done):
        return "todo"
    age = datetime.now() - s.updated_at
    if age <= FRESH_THRESHOLD:
        return "fresh"
    if age <= STALE_THRESHOLD:
        return "warm"
    return "stale"


_TIER_DOT = {
    "todo": "[dim]○[/dim]",
    "fresh": "[green]●[/green]",
    "warm": "[dark_orange]●[/dark_orange]",
    "stale": "[red]●[/red]",
}


def _status_dot(s: Session) -> str:
    return _TIER_DOT[_heartbeat_tier(s)]


def _group_by_status(sessions: list[Session], include_done: bool = False) -> dict[Status, list[Session]]:
    groups: dict[Status, list[Session]] = {s: [] for s in KANBAN_STATUSES}
    if include_done:
        groups[Status.done] = []
    for s in sessions:
        if s.status in groups:
            groups[s.status].append(s)
    return groups


# ---------------------------------------------------------------------------
# Breathing dot (smooth opacity pulse for fresh heartbeats)
# ---------------------------------------------------------------------------

BREATH_PERIOD = 4.0  # seconds per full cycle — calm, human-like
BREATH_MIN_OPACITY = 0.3
BREATH_FPS = 15


class BreathingDot(Static):
    """A status dot that gently pulses opacity when the heartbeat is fresh."""

    DEFAULT_CSS = """
    BreathingDot {
        width: auto;
        height: 1;
    }
    """

    def __init__(self, session: Session, **kwargs: object) -> None:
        super().__init__(_status_dot(session), **kwargs)
        self._breathing = _heartbeat_tier(session) == "fresh"
        self._phase = 0.0

    def on_mount(self) -> None:
        if self._breathing:
            self._timer = self.set_interval(1 / BREATH_FPS, self._breathe)

    def _breathe(self) -> None:
        self._phase += (1 / BREATH_FPS) / BREATH_PERIOD * 2 * math.pi
        mid = (1.0 + BREATH_MIN_OPACITY) / 2
        amp = (1.0 - BREATH_MIN_OPACITY) / 2
        self.styles.text_opacity = mid + amp * math.sin(self._phase)


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
    #h-links {
        width: auto;
        align: right middle;
        layout: horizontal;
    }
    #h-links Link {
        padding: 0 1;
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
            with Container(id="h-links"):
                yield Link("GitHub", url="https://github.com/djetelina/agtrk")
                yield Link("Changelog", url="https://github.com/djetelina/agtrk/blob/main/CHANGELOG.md")

    def update_status(self, sessions: list, view: str, archived: bool) -> None:
        counts: dict[Status, int] = {}
        for s in sessions:
            counts[s.status] = counts.get(s.status, 0) + 1
        stats = "  ".join(f"{STATUS_EMOJI.get(st, '')} {counts.get(st, 0)}" for st in KANBAN_STATUSES)
        self._stats_label.update(stats)
        self._view_label.update(view)
        self._archived_label.update(f"archived: {'on' if archived else 'off'}")

    def update_knowledge_status(self, repo_count: int, total_entries: int, view: str) -> None:
        self._stats_label.update(f"📚 {repo_count} repos  {total_entries} entries")
        self._view_label.update(view)
        self._archived_label.update("")


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
        # Bottom: version fills the 5-char dash slot
        return f"[$accent] ┌─────┐\n[$secondary]│[/$secondary] [$primary]agtrk[/$primary] [$secondary]│[/$secondary]\n[$accent] └{__version__}┘"


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
    with open_db() as conn:
        session = get_session(conn, session_id)

    emoji = STATUS_EMOJI.get(session.status, "")
    lines = [
        f"{emoji} [bold]{session.task}[/bold]",
        "",
        f"  [dim]ID[/dim]        {session.id}",
        f"  [dim]Status[/dim]    {session.status}",
        f"  [dim]Repo[/dim]      {repo_display_name(session.repo) if session.repo else '-'}",
        f"  [dim]Issue[/dim]     {session.issue or '-'}",
        f"  [dim]Created[/dim]   {_time_ago(session.created_at)}  [dim italic]{session.created_at:%Y-%m-%d %H:%M}[/dim italic]",
        f"  [dim]Heartbeat[/dim] {_time_ago(session.updated_at)}  [dim italic]{session.updated_at:%Y-%m-%d %H:%M}[/dim italic]",
    ]
    if session.completed_at:
        completed = session.completed_at
        lines.append(f"  [dim]Done[/dim]      {_time_ago(completed)}  [dim italic]{completed:%Y-%m-%d %H:%M}[/dim italic]")
    if session.summary:
        lines.append("")
        lines.append("[bold]Summary[/bold]")
        lines.append(f"  {session.summary}")
    if session.notes:
        lines.append("")
        lines.append("[bold]Notes[/bold]")
        lines.append("")
        for n in reversed(session.notes):
            meta_parts = [f"[dim]{_time_ago(n.created_at)}[/dim]"]
            tag_parts = []
            if n.repo:
                tag_parts.append(repo_display_name(n.repo))
            if n.branch:
                tag_parts.append(f"@{n.branch}")
            if tag_parts:
                meta_parts.append(f"[dim]\\[{''.join(tag_parts)}][/dim]")
            if n.cwd and n.repo and "/" in n.repo and n.repo.count("/") == 1:
                # Show cwd only when repo is from a remote (org/repo format)
                # — path-fallback repos already convey location
                meta_parts.append(f"[dim italic]~/{n.cwd}[/dim italic]")
            if n.worktree:
                meta_parts.append("\U0001f333")
            lines.append(f"  {'  '.join(meta_parts)}")
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
        task = _truncate(s.task, 40)
        yield Static(f"[bold]{task}[/bold]")
        repo = repo_display_name(s.repo) if s.repo else ""
        with Horizontal(classes="card-meta"):
            yield Static(repo, classes="card-meta-left")
            yield BreathingDot(s, classes="card-meta-right")

    def _open_detail(self) -> None:
        self.app.push_screen(DetailScreen(_build_detail_content(self.session.id)))

    def on_click(self) -> None:
        self._open_detail()

    def key_enter(self) -> None:
        self._open_detail()

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
    .col-header { width: 1fr; height: 1; text-align: center; text-style: bold;
        background: $primary-darken-2; margin: 0 0 1 0; border-left: vkey $accent; }
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
    #table-view { height: 1fr; display: none; }
    #board { width: 1fr; height: 1fr; }
    #board.hidden { display: none; }
    #table-view.visible { display: block; }
    #kb-grid { display: none; }
    #kb-grid.visible { display: block; }
    #kb-detail { display: none; }
    #kb-detail.visible { display: block; }
    """

    BINDINGS = [
        Binding("k", "toggle_knowledge", "Knowledge"),
        Binding("v", "toggle_view", "View"),
        Binding("a", "toggle_archived", "Archived"),
        Binding("escape", "go_back", "Back", show=False),
        Binding("q", "quit", "Quit"),
    ]

    show_archived: reactive[bool] = reactive(False)
    kanban_view: bool = True
    # "sessions" | "kb-grid" | "kb-detail"
    _mode: str = "sessions"
    _sessions: list[Session] = []

    def compose(self) -> ComposeResult:
        with Container(id="header"):
            yield HeaderStatus()
            yield HeaderLogo()
        # Session views
        yield DataTable(id="table-view", cursor_type="row", zebra_stripes=True)
        yield Horizontal(id="board")
        # Knowledge views
        yield RepoGrid(id="kb-grid")
        yield Container(id="kb-detail")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "dracula"
        self._load_data()
        self.set_interval(REFRESH_INTERVAL, self._load_data)
        self.call_later(self.check_for_new_version)
        cols = list(self.query(CardColumn))
        if cols:
            cols[0].focus()

    async def check_for_new_version(self) -> None:
        latest = await get_latest_pypi_version()
        if latest and latest > Version(__version__):
            self.notify(
                f"✨ Version {latest} is available!\n[dim]Update: pipx upgrade agtrk[/dim]",
                timeout=20,
            )

    # --- Header ---

    def _refresh_header(self) -> None:
        header = self.query_one(HeaderStatus)
        if self._mode == "sessions":
            view = "kanban" if self.kanban_view else "table"
            header.update_status(self._sessions, view, self.show_archived)
        elif self._mode == "kb-grid":
            summaries = self._kb_summaries
            total = sum(s.total for s in summaries)
            header.update_knowledge_status(len(summaries), total, "knowledge")
        elif self._mode == "kb-detail":
            summaries = self._kb_summaries
            total = sum(s.total for s in summaries)
            header.update_knowledge_status(len(summaries), total, "knowledge · repo")

    # --- Session data ---

    _kb_summaries: list = []

    def _load_data(self) -> None:
        if self._mode in ("kb-grid", "kb-detail"):
            self._load_knowledge_grid()
            self._refresh_header()
            return
        with open_db() as conn:
            new_sessions = list_sessions(conn, include_archived=self.show_archived)
        old_ids = [s.id for s in self._sessions]
        new_ids = [s.id for s in new_sessions]
        changed = old_ids != new_ids or any(
            (a.status, a.updated_at, a.task, a.repo) != (b.status, b.updated_at, b.task, b.repo)
            for a, b in zip(self._sessions, new_sessions, strict=False)
        )
        self._sessions = new_sessions
        if changed:
            self._load_table()
            self._load_board()
        self._refresh_header()

    def _load_table(self) -> None:
        table = self.query_one("#table-view", DataTable)
        table.clear(columns=True)
        # Fixed content: dot(1) + ID(20) + emoji(2) + Repo(16) + Issue(10) = 49
        # DataTable overhead: 2 chars padding * 6 cols + 1 cursor gutter = 13
        fixed_width = 62
        task_width = max(20, self.size.width - fixed_width)

        table.add_column("", width=1)
        table.add_column("ID", width=20)
        table.add_column("", width=2)
        table.add_column("Task", width=task_width)
        table.add_column("Repo", width=16)
        table.add_column("Issue", width=10)

        for s in self._sessions:
            style = "dim italic" if s.status == Status.done else ""
            emoji = STATUS_EMOJI.get(s.status, "")
            task = _truncate(s.task, task_width)
            table.add_row(
                Text.from_markup(_status_dot(s)),
                Text(s.id, style=style),
                Text(emoji),
                Text(task, style=style),
                Text(repo_display_name(s.repo) if s.repo else "", style=style),
                Text(s.issue or "", style=style),
                key=s.id,
            )

    def _load_board(self) -> None:
        board = self.query_one("#board", Horizontal)
        # Track focused card to restore after rebuild
        focused = self.focused
        focused_id = focused.session.id if isinstance(focused, CardItem) else None
        focused_col_status = None
        if isinstance(focused, CardColumn):
            focused_col_status = focused.status

        board.remove_children()
        groups = _group_by_status(self._sessions, self.show_archived)
        first = True
        restore_target = None
        for status, items in groups.items():
            col = CardColumn(status)
            if first:
                col.add_class("first-col")
                first = False
            if focused_col_status == status:
                restore_target = col
            board.mount(col)
            for s in items:
                card = CardItem(s)
                col.mount(card)
                if s.id == focused_id:
                    restore_target = card

        if restore_target is not None:
            self.call_after_refresh(restore_target.focus)

    # --- Knowledge ---

    def _load_knowledge_grid(self) -> None:
        with open_db() as conn:
            self._kb_summaries = list_knowledge_repos(conn)
        self.query_one(RepoGrid).load(self._kb_summaries)

    def _open_repo_detail(self, repo: str) -> None:
        self._mode = "kb-detail"
        self.query_one("#kb-grid").remove_class("visible")
        detail_container = self.query_one("#kb-detail", Container)
        detail_container.remove_children()
        detail_view = RepoDetailView(repo)
        detail_container.mount(detail_view)
        detail_container.add_class("visible")
        self._refresh_header()

    # --- View switching ---

    def _show_sessions(self) -> None:
        self._mode = "sessions"
        self.query_one("#kb-grid").remove_class("visible")
        self.query_one("#kb-detail").remove_class("visible")
        if self.kanban_view:
            self.query_one("#board").remove_class("hidden")
            cols = list(self.query(CardColumn))
            if cols:
                cols[0].focus()
        else:
            self.query_one("#table-view").add_class("visible")
            self.query_one("#table-view", DataTable).focus()
        self._refresh_header()

    def _show_knowledge_grid(self) -> None:
        self._mode = "kb-grid"
        # Hide session views
        self.query_one("#board").add_class("hidden")
        self.query_one("#table-view").remove_class("visible")
        self.query_one("#kb-detail").remove_class("visible")
        # Show and load grid
        self.query_one("#kb-grid").add_class("visible")
        self._load_knowledge_grid()
        self._refresh_header()
        self._focus_first_tile()

    def _focus_first_tile(self) -> None:
        def _do_focus() -> None:
            tiles = list(self.query(RepoTile))
            if tiles:
                tiles[0].focus()

        self.call_after_refresh(_do_focus)

    # --- Event handlers ---

    def on_resize(self) -> None:
        if self._mode == "sessions" and not self.kanban_view:
            self._load_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is None:
            return
        self.push_screen(DetailScreen(_build_detail_content(event.row_key.value)))

    # --- Actions ---

    def action_open_repo(self, repo: str) -> None:
        self._open_repo_detail(repo)

    def action_go_back(self) -> None:
        if self._mode == "kb-detail":
            self._show_knowledge_grid()
        elif self._mode == "kb-grid":
            self._show_sessions()
        elif self._mode == "sessions" and self.kanban_view:
            focused = self.focused
            if isinstance(focused, CardItem):
                for a in focused.ancestors_with_self:
                    if isinstance(a, CardColumn):
                        a.focus()
                        return

    def action_toggle_archived(self) -> None:
        if self._mode != "sessions":
            return
        self.show_archived = not self.show_archived
        self._load_data()

    def action_toggle_view(self) -> None:
        if self._mode != "sessions":
            return
        self.kanban_view = not self.kanban_view
        self.query_one("#table-view").toggle_class("visible")
        self.query_one("#board").toggle_class("hidden")
        if self.kanban_view:
            cols = list(self.query(CardColumn))
            if cols:
                cols[0].focus()
        else:
            self.query_one("#table-view", DataTable).focus()
        self._refresh_header()

    def action_toggle_knowledge(self) -> None:
        if self._mode == "sessions":
            self._show_knowledge_grid()
        else:
            self._show_sessions()


def run_tui() -> None:
    app = SessionDashboard()
    app.run()
