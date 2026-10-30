"""Exercise sync preparation using local Git repositories, without network or credentials."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "prepare_upstream_sync", Path(__file__).resolve().parents[1] / "scripts/prepare_upstream_sync.py",
)
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-m", name)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-b", "main")
    git(upstream, "config", "user.name", "Test")
    git(upstream, "config", "user.email", "test@example.invalid")
    commit(upstream, "shared.txt", "base\n")
    personal = tmp_path / "personal"
    git(tmp_path, "clone", str(upstream), str(personal))
    git(personal, "config", "user.name", "Test")
    git(personal, "config", "user.email", "test@example.invalid")
    git(personal, "switch", "-c", sync.BRANCH)
    commit(personal, "feature.txt", "personal feature\n")
    monkeypatch.chdir(personal)
    return upstream, personal


def test_noop_keeps_personal_commit(repos):
    upstream, personal = repos
    before = git(personal, "rev-parse", "HEAD")
    assert sync.prepare(str(upstream)) is False
    assert git(personal, "rev-parse", "HEAD") == before
    assert git(personal, "status", "--porcelain") == ""


def test_clean_merge_waits_for_validation_and_retains_personal_changes(repos):
    upstream, personal = repos
    before = git(personal, "rev-parse", "HEAD")
    commit(upstream, "upstream.txt", "upstream update\n")
    assert sync.prepare(str(upstream)) is True
    assert (personal / "feature.txt").read_text() == "personal feature\n"
    assert (personal / "upstream.txt").read_text() == "upstream update\n"
    # Even a successful merge is not committed or published before checks pass.
    assert git(personal, "rev-parse", "HEAD") == before
    git(personal, "commit", "-m", "sync after passing checks")
    assert len(git(personal, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3


def test_conflict_fails_without_advancing_either_branch(repos):
    upstream, personal = repos
    commit(personal, "shared.txt", "personal edit\n")
    commit(upstream, "shared.txt", "upstream edit\n")
    before = git(personal, "rev-parse", "HEAD")
    source = git(upstream, "rev-parse", "HEAD")
    with pytest.raises(subprocess.CalledProcessError):
        sync.prepare(str(upstream))
    assert git(personal, "rev-parse", "HEAD") == before
    assert git(upstream, "rev-parse", "HEAD") == source
    assert "UU shared.txt" in git(personal, "status", "--porcelain")


def test_dirty_checkout_and_wrong_branch_are_rejected(repos):
    upstream, personal = repos
    (personal / "feature.txt").write_text("unsaved", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean"):
        sync.prepare(str(upstream))
    git(personal, "restore", "feature.txt")
    git(personal, "switch", "main")
    with pytest.raises(RuntimeError, match="Expected"):
        sync.prepare(str(upstream))
