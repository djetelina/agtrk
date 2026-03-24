"""Tests for agtrk.git — uses real temp git repos, no mocking."""

import subprocess
from pathlib import Path

import pytest

from agtrk.git import detect_branch, detect_cwd, detect_repo, detect_worktree, repo_display_name


class TestDetectRepo:
    def test_https_remote(self, git_repo_with_remote):
        assert detect_repo() == "acme/widgets"

    def test_ssh_remote(self, git_repo, monkeypatch):
        subprocess.run(
            ["git", "-C", str(git_repo), "remote", "add", "origin", "git@github.com:org/my-repo.git"],
            check=True,
            capture_output=True,
        )
        assert detect_repo() == "org/my-repo"

    def test_no_remote_falls_back_to_path(self, git_repo, monkeypatch):
        """No origin remote -> cwd relative to HOME."""
        home = git_repo.parent
        monkeypatch.setenv("HOME", str(home))
        result = detect_repo()
        assert result == git_repo.name

    def test_not_a_git_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert detect_repo() is None


class TestDetectBranch:
    def test_on_main(self, git_repo):
        branch = detect_branch()
        assert branch in ("main", "master")

    def test_on_feature_branch(self, git_repo):
        subprocess.run(["git", "-C", str(git_repo), "checkout", "-b", "feat/cool"], check=True, capture_output=True)
        assert detect_branch() == "feat/cool"

    def test_not_a_git_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert detect_branch() is None


class TestDetectCwd:
    def test_under_home(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        home = tmp_path.parent
        monkeypatch.setenv("HOME", str(home))
        assert detect_cwd() == tmp_path.name

    def test_not_under_home(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", "/nonexistent-home-dir")
        result = detect_cwd()
        assert result == str(tmp_path)


class TestDetectWorktree:
    def test_main_checkout_is_false(self, git_repo):
        assert detect_worktree() is False

    def test_worktree_is_true(self, git_repo, tmp_path):
        wt_path = tmp_path / "my-worktree"
        subprocess.run(
            ["git", "-C", str(git_repo), "worktree", "add", str(wt_path), "-b", "wt-branch"],
            check=True,
            capture_output=True,
        )
        import os

        os.chdir(wt_path)
        assert detect_worktree() is True

    def test_not_a_git_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert detect_worktree() is None


class TestRepoDisplayName:
    def test_org_repo(self):
        assert repo_display_name("acme/widgets") == "widgets"

    def test_plain_name(self):
        assert repo_display_name("widgets") == "widgets"

    def test_path_fallback_deep(self):
        assert repo_display_name("Documents/personal/my-project") == ".../personal/my-project"

    def test_path_fallback_two_segments(self):
        assert repo_display_name("personal/my-project") == "my-project"
