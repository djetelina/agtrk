"""Knowledge browser widgets for the agtrk TUI."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ItemGrid, VerticalScroll
from textual.widgets import Static, Tree

from agtrk.db import open_db
from agtrk.models import Kind, Knowledge
from agtrk.service import RepoKnowledgeSummary, recall

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KIND_COLOR: dict[Kind, str] = {
    Kind.architecture: "#ff79c6",
    Kind.decision: "#8be9fd",
    Kind.convention: "#50fa7b",
    Kind.exploration: "#ffb86c",
}

KIND_EMOJI: dict[Kind, str] = {
    Kind.architecture: "🏗",
    Kind.decision: "⚖️",
    Kind.convention: "📏",
    Kind.exploration: "🔍",
}

_BAR_CHAR = "▒"

_SECONDS_PER_MINUTE = 60
_MINUTES_PER_HOUR = 60
_HOURS_PER_DAY = 24


def _time_ago(dt: datetime) -> str:
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < _SECONDS_PER_MINUTE:
        return "just now"
    minutes = seconds // _SECONDS_PER_MINUTE
    if minutes < _MINUTES_PER_HOUR:
        return f"{minutes}m ago"
    hours = minutes // _MINUTES_PER_HOUR
    if hours < _HOURS_PER_DAY:
        return f"{hours}h ago"
    days = hours // _HOURS_PER_DAY
    return f"{days}d ago"


def _split_repo(repo: str) -> tuple[str, str]:
    """Split 'org/repo' into (org, repo). Falls back to ('', repo)."""
    if "/" in repo:
        parts = repo.split("/", 1)
        return parts[0], parts[1]
    return "", repo


# ---------------------------------------------------------------------------
# Repo tile
# ---------------------------------------------------------------------------


class RepoTile(Static):
    """A grid tile representing a repository's knowledge summary."""

    DEFAULT_CSS = """
    RepoTile {
        width: 1fr;
        height: 7;
        padding: 0 1;
        border: solid $surface-darken-1;
    }
    RepoTile:focus {
        border: solid $accent;
    }
    RepoTile:hover {
        background: $primary-darken-1;
    }
    """
    can_focus = True
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("up", "grid_up", show=False),
        Binding("down", "grid_down", show=False),
        Binding("left", "grid_left", show=False),
        Binding("right", "grid_right", show=False),
    ]

    def __init__(self, summary: RepoKnowledgeSummary) -> None:
        super().__init__()
        self.summary = summary

    def _all_tiles(self) -> list[RepoTile]:
        return list(self.app.query(RepoTile))

    def _my_index(self) -> int:
        return self._all_tiles().index(self)

    def _cols_per_row(self) -> int:
        """Estimate columns per row from tile positions."""
        tiles = self._all_tiles()
        if len(tiles) <= 1:
            return 1
        first_y = tiles[0].region.y
        for i, tile in enumerate(tiles[1:], 1):
            if tile.region.y != first_y:
                return i
        return len(tiles)

    def _focus_index(self, idx: int) -> None:
        tiles = self._all_tiles()
        if 0 <= idx < len(tiles):
            tiles[idx].focus()

    def action_grid_left(self) -> None:
        idx = self._my_index()
        if idx > 0:
            self._focus_index(idx - 1)

    def action_grid_right(self) -> None:
        idx = self._my_index()
        self._focus_index(idx + 1)

    def action_grid_up(self) -> None:
        idx = self._my_index()
        cols = self._cols_per_row()
        self._focus_index(idx - cols)

    def action_grid_down(self) -> None:
        idx = self._my_index()
        cols = self._cols_per_row()
        self._focus_index(idx + cols)

    def key_enter(self) -> None:
        self.app.action_open_repo(self.summary.repo)

    def on_click(self) -> None:
        self.app.action_open_repo(self.summary.repo)

    def render(self) -> Text:
        s = self.summary
        org, name = _split_repo(s.repo)

        lines: list[Text] = []

        # Line 1: dim org
        if org:
            lines.append(Text(org, style="dim"))
        else:
            lines.append(Text(""))

        # Line 2: bold repo name
        lines.append(Text(name, style="bold"))

        # Line 3: color bar
        bar = self._render_bar(s.counts, s.total)
        lines.append(bar)

        # Line 4: emoji counts + age
        meta_parts = []
        for kind in Kind:
            count = s.counts.get(kind, 0)
            if count > 0:
                meta_parts.append(f"{KIND_EMOJI[kind]} {count}")
        meta_parts.append(f"· {_time_ago(s.latest_updated)}")
        lines.append(Text(" ".join(meta_parts), style="dim"))

        return Text("\n").join(lines)

    def _render_bar(self, counts: dict[Kind, int], total: int) -> Text:
        """Render a proportional ▒ bar colored by kind."""
        # Use available width minus padding/border (approximate)
        bar_width = max(10, self.size.width - 4)
        bar = Text()
        for kind in Kind:
            count = counts.get(kind, 0)
            if count > 0:
                segment_width = max(1, round(count / total * bar_width))
                bar.append(_BAR_CHAR * segment_width, style=KIND_COLOR[kind])
        return bar


# ---------------------------------------------------------------------------
# Repo grid
# ---------------------------------------------------------------------------


class RepoGrid(Container):
    """Grid of RepoTile widgets, one per repository."""

    DEFAULT_CSS = """
    RepoGrid {
        width: 1fr;
        height: 1fr;
    }
    RepoGrid > ItemGrid {
        width: 1fr;
        height: auto;
    }
    RepoGrid > .kb-legend {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield ItemGrid(min_column_width=28, max_column_width=40, id="repo-grid")
        legend_parts = []
        for kind in Kind:
            legend_parts.append(f"[{KIND_COLOR[kind]}]■[/] {kind.value}")
        legend_parts.append("  ←↑↓→ navigate · ↵ open · Esc back")
        yield Static("  ".join(legend_parts), classes="kb-legend")

    def load(self, summaries: list[RepoKnowledgeSummary]) -> None:
        grid = self.query_one("#repo-grid", ItemGrid)
        grid.remove_children()
        for s in summaries:
            grid.mount(RepoTile(s))


# ---------------------------------------------------------------------------
# Entry tree + preview (split view)
# ---------------------------------------------------------------------------


class KnowledgeTree(Tree[Knowledge]):
    """Tree widget showing knowledge entries grouped by kind."""

    DEFAULT_CSS = """
    KnowledgeTree {
        width: 1fr;
        height: 1fr;
        scrollbar-size: 1 1;
        border-right: solid $surface-darken-1;
    }
    KnowledgeTree:focus {
        border-right: solid $accent;
    }
    """

    def __init__(self, repo: str) -> None:
        super().__init__(repo, id="kb-tree")
        self.repo = repo
        self.show_root = False


class EntryPreview(VerticalScroll):
    """Right panel showing the selected knowledge entry content."""

    DEFAULT_CSS = """
    EntryPreview {
        width: 2fr;
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """
    can_focus = True

    def compose(self) -> ComposeResult:
        yield Static("", id="kb-preview-content")

    def show_entry(self, entry: Knowledge) -> None:
        content = self.query_one("#kb-preview-content", Static)
        color = KIND_COLOR.get(entry.kind, "")
        lines = [
            f"[{color}]{KIND_EMOJI.get(entry.kind, '')} {entry.kind.value}[/] · updated {_time_ago(entry.updated_at)}",
            "",
            f"[bold]{entry.title}[/bold]",
            "",
            entry.content,
        ]
        content.update("\n".join(lines))

    def clear(self) -> None:
        content = self.query_one("#kb-preview-content", Static)
        content.update("[dim]Select an entry to preview[/dim]")


class RepoDetailView(Container):
    """Split view: tree on the left, preview on the right."""

    DEFAULT_CSS = """
    RepoDetailView {
        width: 1fr;
        height: 1fr;
    }
    RepoDetailView > Horizontal {
        width: 1fr;
        height: 1fr;
    }
    RepoDetailView > .kb-repo-header {
        dock: top;
        height: 1;
        padding: 0 1;
        background: $accent;
        text-style: bold;
    }
    RepoDetailView > .kb-detail-footer {
        dock: bottom;
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("tab", "switch_pane", "Switch pane", show=False),
    ]

    def __init__(self, repo: str) -> None:
        super().__init__()
        self.repo = repo

    def compose(self) -> ComposeResult:
        yield Static(f"📁 {self.repo}", classes="kb-repo-header")
        with Horizontal():
            yield KnowledgeTree(self.repo)
            yield EntryPreview()
        yield Static(
            "↑↓ navigate · ↵ expand/collapse · Tab switch pane · Esc back to repos",
            classes="kb-detail-footer",
        )

    def on_mount(self) -> None:
        self._load_entries()
        tree = self.query_one(KnowledgeTree)
        tree.focus()

    def _load_entries(self) -> None:
        tree = self.query_one(KnowledgeTree)
        tree.clear()
        preview = self.query_one(EntryPreview)
        preview.clear()

        with open_db() as conn:
            entries = recall(conn, self.repo)

        # Group by kind
        by_kind: dict[Kind, list[Knowledge]] = {k: [] for k in Kind}
        for entry in entries:
            by_kind[entry.kind].append(entry)

        for kind in Kind:
            items = by_kind[kind]
            if not items:
                continue
            color = KIND_COLOR[kind]
            emoji = KIND_EMOJI[kind]
            branch = tree.root.add(
                Text.from_markup(f"[{color}]{emoji} {kind.value}[/] ({len(items)})"),
                expand=True,
            )
            for entry in items:
                branch.add_leaf(entry.title, data=entry)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[Knowledge]) -> None:
        preview = self.query_one(EntryPreview)
        if event.node.data is not None:
            preview.show_entry(event.node.data)
        else:
            preview.clear()

    def action_switch_pane(self) -> None:
        tree = self.query_one(KnowledgeTree)
        preview = self.query_one(EntryPreview)
        if tree.has_focus:
            preview.focus()
        else:
            tree.focus()
