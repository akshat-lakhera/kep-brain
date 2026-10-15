"""ensure_repo against a tiny local bare repository standing in for the public remote."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.ingest.repos import RepoError, ensure_repo
from app.settings import Settings


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        capture_output=True,
        check=True,
        text=True,
    )
    return out.stdout.strip()


def _commit(work: Path, name: str) -> str:
    (work / f"{name}.txt").write_text(name, encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", name)
    _git(work, "push", "origin", "HEAD")
    return _git(work, "rev-parse", "HEAD")


@pytest.fixture
def remote(tmp_path: Path) -> tuple[Path, Path]:
    bare = tmp_path / "remote.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-b", "main")
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "main")
    _git(work, "remote", "add", "origin", str(bare))
    return bare, work


def _settings(tmp_path: Path, bare: Path, **extra: str | None) -> Settings:
    return Settings(
        _env_file=None,
        repo_cache_dir=str(tmp_path / "cache"),
        enhancements_repo_url=str(bare),
        community_repo_url=str(bare),
        **extra,  # type: ignore[arg-type]
    )


def test_clones_when_missing_and_returns_head(tmp_path: Path, remote: tuple[Path, Path]) -> None:
    bare, work = remote
    first = _commit(work, "a")
    settings = _settings(tmp_path, bare)
    assert not (tmp_path / "cache" / "enhancements").exists()
    assert ensure_repo(settings, "enhancements") == first
    assert (tmp_path / "cache" / "enhancements" / ".git").exists()
    assert not (tmp_path / "cache" / "enhancements" / "a.txt").exists()  # no working tree written


def test_fetches_when_present_and_follows_new_head(tmp_path: Path, remote: tuple[Path, Path]) -> None:
    bare, work = remote
    _commit(work, "a")
    settings = _settings(tmp_path, bare)
    ensure_repo(settings, "community")
    second = _commit(work, "b")
    assert ensure_repo(settings, "community") == second


def test_pin_is_honoured_even_when_remote_moves(tmp_path: Path, remote: tuple[Path, Path]) -> None:
    bare, work = remote
    first = _commit(work, "a")
    _commit(work, "b")
    settings = _settings(tmp_path, bare, enhancements_pin_sha=first)
    assert ensure_repo(settings, "enhancements") == first


def test_unknown_pin_is_a_clear_error(tmp_path: Path, remote: tuple[Path, Path]) -> None:
    bare, work = remote
    _commit(work, "a")
    settings = _settings(tmp_path, bare, enhancements_pin_sha="0" * 40)
    with pytest.raises(RepoError, match="resolve pin"):
        ensure_repo(settings, "enhancements")


def test_unreachable_remote_is_a_clear_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tmp_path / "missing.git")
    with pytest.raises(RepoError, match="git clone"):
        ensure_repo(settings, "enhancements")
    assert not (tmp_path / "cache" / "enhancements").exists()


def test_owners_full_sha_pin_needs_no_network(tmp_path: Path, remote: tuple[Path, Path]) -> None:
    bare, _ = remote
    sha = "ab" * 20
    assert ensure_repo(_settings(tmp_path, bare, owners_pin_sha=sha), "owners") == sha
