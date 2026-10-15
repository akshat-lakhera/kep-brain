"""Locate the public source repositories and resolve the commit a sync reads.

Nothing is assumed to exist on disk: a missing clone is made, a present one is
fetched (never checked out, so its working tree is untouched). Each source
resolves to one full commit SHA: the configured pin when set, else the head of
the remote's default branch at the moment of the call.

kubernetes/enhancements and kubernetes/community are cloned under
`REPO_CACHE_DIR`; kubernetes/kubernetes is not (its OWNERS layer is read through
the GitHub API), so only its head SHA is resolved, through the API.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import structlog

from app.ingest.github import GitHubError, resolve_token
from app.settings import Settings

log = structlog.get_logger(__name__)

RepoName = Literal["enhancements", "community", "owners"]
GITHUB_API = "https://api.github.com"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class RepoError(RuntimeError):
    """A source repository could not be cloned, fetched or resolved."""


@dataclass(frozen=True)
class _Spec:
    url: str
    pin: str | None
    clone_args: tuple[str, ...]


def _spec(settings: Settings, name: RepoName) -> _Spec:
    if name == "enhancements":
        return _Spec(settings.enhancements_repo_url, settings.enhancements_pin_sha, ())
    if name == "community":
        # Only sigs.yaml is read from it, so file contents are fetched on demand.
        return _Spec(settings.community_repo_url, settings.community_pin_sha, ("--filter=blob:none",))
    return _Spec(settings.owners_repo_url, settings.owners_pin_sha, ())


def clone_path(settings: Settings, name: Literal["enhancements", "community"]) -> Path:
    return Path(settings.repo_cache_dir) / name


def _git(args: list[str], cwd: Path | None, timeout: int, what: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            check=True,
            env=_git_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RepoError(f"{what} timed out after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise RepoError(f"{what} failed: {detail[-1] if detail else exc.returncode}") from exc
    except FileNotFoundError as exc:
        raise RepoError("git is not installed") from exc
    return out.stdout.decode("utf-8", errors="replace").strip()


def _git_env() -> dict[str, str]:
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def _clone(spec: _Spec, dest: Path, timeout: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    log.info("repo_clone", url=spec.url, dest=str(dest))
    # --no-checkout: only the object database is read, so no working tree is written.
    _git(["clone", "--no-checkout", *spec.clone_args, spec.url, str(tmp)], None, timeout * 3, f"git clone {spec.url}")
    tmp.rename(dest)


def _default_head(root: Path, timeout: int) -> str:
    """Commit of origin's default branch, by ref (no checkout)."""
    try:
        return _git(["rev-parse", "--verify", "origin/HEAD^{commit}"], root, timeout, "resolve origin/HEAD")
    except RepoError:
        _git(["remote", "set-head", "origin", "--auto"], root, timeout, "git remote set-head")
        return _git(["rev-parse", "--verify", "origin/HEAD^{commit}"], root, timeout, "resolve origin/HEAD")


def _ensure_clone(spec: _Spec, root: Path, timeout: int) -> str:
    if not (root / ".git").exists():
        _clone(spec, root, timeout)
    else:
        log.info("repo_fetch", url=spec.url, dest=str(root))
        _git(["fetch", "--prune", "origin"], root, timeout, f"git fetch in {root}")
    if spec.pin:
        sha = _git(["rev-parse", "--verify", f"{spec.pin}^{{commit}}"], root, timeout, f"resolve pin {spec.pin}")
        return sha
    return _default_head(root, timeout)


def _slug(url: str) -> str:
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if match is None:
        raise RepoError(f"not a GitHub repository URL: {url}")
    return match.group(1)


def _api_commit(settings: Settings, url: str, ref: str) -> str:
    slug = _slug(url)
    headers = {"Accept": "application/vnd.github.sha", "User-Agent": "kep-brain-worker"}
    try:
        headers["Authorization"] = f"bearer {resolve_token(settings)}"
    except GitHubError:
        log.warning("repo_api_unauthenticated", repo=slug)
    try:
        resp = httpx.get(
            f"{GITHUB_API}/repos/{slug}/commits/{ref}", headers=headers, timeout=settings.git_timeout_seconds
        )
    except httpx.HTTPError as exc:
        raise RepoError(f"GitHub API request for {slug}@{ref} failed: {exc}") from exc
    sha = resp.text.strip()
    if resp.status_code != 200 or not _FULL_SHA.match(sha):
        raise RepoError(f"GitHub API could not resolve {slug}@{ref} (HTTP {resp.status_code})")
    return sha


def ensure_repo(settings: Settings, name: RepoName) -> str:
    """Make `name` available and return the full commit SHA to read.

    enhancements/community: clone when missing, else `git fetch --prune origin`.
    owners: no clone; the SHA comes from the GitHub API.
    """
    spec = _spec(settings, name)
    timeout = settings.git_timeout_seconds
    if name == "owners":
        if spec.pin and _FULL_SHA.match(spec.pin):
            return spec.pin
        return _api_commit(settings, spec.url, spec.pin or "HEAD")
    sha = _ensure_clone(spec, clone_path(settings, name), timeout)
    log.info("repo_resolved", repo=name, sha=sha, pinned=bool(spec.pin))
    return sha
