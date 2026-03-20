"""Git context auto-detection for claude-sessions."""

import subprocess
from pathlib import Path


def _run_git(*args: str) -> str | None:
    """Run a git command, return stripped stdout or None on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def detect_repo() -> str | None:
    """Detect the repository from git origin remote.

    Parses HTTPS and SSH URLs into 'org/repo' format.
    Falls back to cwd relative to $HOME when no remote exists.
    Returns None if not in a git repo at all.
    """
    if _run_git("rev-parse", "--git-dir") is None:
        return None

    url = _run_git("remote", "get-url", "origin")
    if url is not None:
        return _parse_remote_url(url)

    return _path_relative_to_home(Path.cwd())


def _parse_remote_url(url: str) -> str:
    """Extract 'org/repo' from a git remote URL."""
    if "://" in url:
        path = url.split("//", 1)[-1]
        parts = path.split("/", 1)
        path = parts[1] if len(parts) > 1 else path
    else:
        # SSH-style: git@host:org/repo.git
        path = url.split(":")[-1]

    if path.endswith(".git"):
        path = path[:-4]

    return path


def _path_relative_to_home(path: Path) -> str:
    """Return path relative to $HOME, or absolute if not under $HOME."""
    home = Path.home()
    try:
        return str(path.relative_to(home))
    except ValueError:
        return str(path)


def detect_branch() -> str | None:
    """Detect the current git branch. Returns None if not in a git repo."""
    return _run_git("rev-parse", "--abbrev-ref", "HEAD")


def detect_cwd() -> str:
    """Return cwd relative to $HOME, or absolute path if not under $HOME."""
    return _path_relative_to_home(Path.cwd())


def detect_worktree() -> bool | None:
    """Detect if inside a git worktree.

    Compares --git-dir with --git-common-dir. If they differ, we're in a worktree.
    Returns None if not in a git repo.
    """
    git_dir = _run_git("rev-parse", "--git-dir")
    if git_dir is None:
        return None
    common_dir = _run_git("rev-parse", "--git-common-dir")
    if common_dir is None:
        return None
    git_dir_resolved = Path(git_dir).resolve()
    common_dir_resolved = Path(common_dir).resolve()
    return git_dir_resolved != common_dir_resolved


def repo_display_name(repo: str) -> str:
    """Extract short display name from a repo string.

    'acme/widgets' -> 'widgets'  (org/repo format — just repo name)
    'Documents/personal/my-project' -> '.../personal/my-project'  (path fallback)
    'personal/my-project' -> 'personal/my-project'  (2 segments kept as-is)
    'widgets' -> 'widgets'
    """
    parts = repo.split("/")
    if len(parts) <= 2:
        # org/repo or plain name — show just the repo name
        return parts[-1]
    # Path fallback (3+ segments) — show last 2 with ... prefix
    return f".../{parts[-2]}/{parts[-1]}"
