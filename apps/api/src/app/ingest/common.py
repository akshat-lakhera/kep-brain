"""Shared helpers for the doc-layer ingest: git access, URLs, time and edge envelopes.

All repository reads go through the local clones in `REPO_CACHE_DIR` at a pinned
commit (ADR 0007). Blobs are read through one `git cat-file --batch` process so a
full history replay costs a handful of process spawns, not thousands.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schema.labels import BOT_LOGINS, VALID_TO_OPEN

ENHANCEMENTS_REPO = "kubernetes/enhancements"
COMMUNITY_REPO = "kubernetes/community"
GITHUB = "https://github.com"


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def blob_url(repo: str, sha: str, path: str) -> str:
    return f"{GITHUB}/{repo}/blob/{sha}/{path}"


def tree_url(repo: str, sha: str, path: str) -> str:
    return f"{GITHUB}/{repo}/tree/{sha}/{path}"


def commit_url(repo: str, sha: str) -> str:
    return f"{GITHUB}/{repo}/commit/{sha}"


def pr_url(repo: str, number: int) -> str:
    return f"{GITHUB}/{repo}/pull/{number}"


def person_url(login: str) -> str:
    return f"{GITHUB}/{login}"


def normalise_login(raw: object) -> str | None:
    """`"@SergeyKanzhelev"` -> `sergeykanzhelev`; placeholders and non-handles -> None."""
    if not isinstance(raw, str):
        return None
    text = raw.split("#", 1)[0].strip().strip("'\"").strip()
    text = text.lstrip("@").strip()
    if not text or " " in text or text.upper() in {"TBD", "N/A", "NONE", "TODO"}:
        return None
    if not all(c.isalnum() or c in "-_[]" for c in text):
        return None
    return text.lower()


def is_bot(login: str) -> bool:
    return login.endswith("[bot]") or login in BOT_LOGINS


def path_weight(*labels: str, bot: bool = False) -> int:
    """Edge weight `w` for path search (03 §5.0)."""
    if bot or any(label in {"Release", "Label"} for label in labels):
        return 50
    if any(label in {"SIG", "WorkingGroup", "Committee"} for label in labels):
        return 4
    return 1


def state_props(valid_from: int, valid_to: int, source_url: str, basis: str = "git_history") -> dict[str, Any]:
    return {
        "valid_from": valid_from,
        "valid_from_iso": iso(valid_from),
        "valid_to": valid_to,
        "valid_to_iso": iso(valid_to),
        "valid_from_basis": basis,
        "source_url": source_url,
    }


def open_state_props(valid_from: int, source_url: str, basis: str = "git_history") -> dict[str, Any]:
    return state_props(valid_from, VALID_TO_OPEN, source_url, basis)


class Git:
    """Thin wrapper over a local clone; thread-safe blob reads via one `cat-file --batch`."""

    def __init__(self, root: Path) -> None:
        if not (root / ".git").exists():
            raise FileNotFoundError(f"not a git clone: {root}")
        self.root = root
        self._batch: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def run(self, *args: str) -> str:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=self.root,
            capture_output=True,
            check=True,
        )
        return out.stdout.decode("utf-8", errors="replace")

    def head(self) -> str:
        return self.run("rev-parse", "HEAD").strip()

    def resolve(self, rev: str) -> str:
        return self.run("rev-parse", "--verify", f"{rev}^{{commit}}").strip()

    def commit_time(self, rev: str) -> int:
        return int(self.run("log", "-1", "--format=%at", rev).strip())

    def ls_tree(self, rev: str, *paths: str) -> dict[str, tuple[str, str]]:
        """path -> (mode, blob sha) for every file under `paths` at `rev`."""
        out = self.run("ls-tree", "-r", rev, "--", *paths)
        result: dict[str, tuple[str, str]] = {}
        for line in out.splitlines():
            meta, _, path = line.partition("\t")
            mode, _kind, sha = meta.split()
            result[path] = (mode, sha)
        return result

    def _ensure_batch(self) -> subprocess.Popen[bytes]:
        if self._batch is None or self._batch.poll() is not None:
            self._batch = subprocess.Popen(
                ["git", "cat-file", "--batch"],
                cwd=self.root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        return self._batch

    def read(self, rev: str, path: str) -> str | None:
        """Content of `path` at `rev`, or None when it does not exist there."""
        with self._lock:
            proc = self._ensure_batch()
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(f"{rev}:{path}\n".encode())
            proc.stdin.flush()
            header = proc.stdout.readline().decode().strip()
            if header.endswith("missing") or header.endswith("ambiguous"):
                return None
            size = int(header.split()[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)  # trailing newline
        return data.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self._batch is not None and self._batch.poll() is None:
            assert self._batch.stdin is not None
            self._batch.stdin.close()
            self._batch.wait(timeout=10)
        self._batch = None


@dataclass(frozen=True)
class Revision:
    """One commit that touched a file, oldest-first order is the caller's job."""

    sha: str
    at: int
    subject: str
    path: str  # the file's path at that commit (follows renames)


def _same_document(old: str, new: str) -> bool:
    """A rename continues a file's history only within the same KEP (same directory name or number).

    `git log --follow` also follows copies and template-similar files (`kep.yaml`s
    are short and alike), which would graft another KEP's history onto this one.
    """
    old_dir, new_dir = old.rsplit("/", 2)[-2], new.rsplit("/", 2)[-2]
    if old_dir == new_dir:
        return True
    old_num, new_num = old_dir.split("-", 1)[0], new_dir.split("-", 1)[0]
    return old_num.isdigit() and old_num == new_num


def file_revisions(git: Git, rev: str, path: str) -> list[Revision]:
    """Every non-merge commit that changed `path`, following genuine renames only, oldest first."""
    out = git.run("log", "--follow", "--name-status", "--format=@@%H%x09%at%x09%s", rev, "--", path)
    revisions: list[Revision] = []
    current: tuple[str, int, str] | None = None
    for line in out.splitlines():
        if line.startswith("@@"):
            sha, at, subject = line[2:].split("	", 2)
            current = (sha, int(at), subject)
            continue
        if not line.strip() or current is None:
            continue
        parts = line.split("	")
        status = parts[0][:1]
        new_path = parts[-1]
        revisions.append(Revision(sha=current[0], at=current[1], subject=current[2], path=new_path))
        current = None
        if status == "C" or (status == "R" and not _same_document(parts[1], new_path)):
            break  # this commit created our file from another one; older entries are not ours
    revisions.reverse()
    return revisions
