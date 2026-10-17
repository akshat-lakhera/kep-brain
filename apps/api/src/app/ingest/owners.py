"""OWNERS layer: OWNERS files of the directories the in-scope SIGs maintain (see `select_owners`) plus
the root `OWNERS_ALIASES` (03 §4.1, §5.1).

Files come from the GitHub contents API at one `kubernetes/kubernetes` commit (the default-branch head at
sync start unless OWNERS_PIN_SHA is set; the repository is never cloned) and are cached under
`<REPO_CACHE_DIR>/owners/<sha>/`. Ownership is a snapshot source, so
every state edge starts at first observation (`valid_from_basis = first_observed`) and a later sync closes
the edges the file no longer lists (03 §7.6).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx
import structlog
import yaml

from app.db.batch import BatchWriter
from app.ingest.common import Git, blob_url, is_bot, iso, normalise_login, open_state_props, person_url
from app.ingest.github import resolve_token
from app.ingest.repos import clone_path, ensure_repo
from app.ingest.sigs import SIGS_PATH, OrgChart, parse_sigs_yaml
from app.schema.labels import VALID_TO_OPEN
from app.settings import Settings

log = structlog.get_logger(__name__)

KK_REPO = "kubernetes/kubernetes"
ALIASES_PATH = "OWNERS_ALIASES"
API = "https://api.github.com"


@dataclass
class OwnersFile:
    path: str  # repository path of the file, e.g. pkg/kubelet/OWNERS
    directory: str  # "" for the repository root
    blob_sha: str
    text: str
    approvers: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    emeritus: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    no_parent_owners: bool = False
    filters_raw: str | None = None


def _names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: dict[str, None] = {}
    for item in value:
        login = normalise_login(item)
        if login:
            seen.setdefault(login, None)
    return list(seen)


def parse_owners(path: str, blob_sha: str, text: str) -> OwnersFile:
    """Top-level lists and the `.*` filter block are ingested; any other filter is kept as raw text."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        data = {}
    directory = str(PurePosixPath(path).parent)
    parsed = OwnersFile(path=path, directory="" if directory == "." else directory, blob_sha=blob_sha, text=text)
    blocks: list[dict[str, Any]] = [data]
    filters = data.get("filters")
    other: dict[str, Any] = {}
    if isinstance(filters, dict):
        for pattern, block in filters.items():
            if pattern == ".*" and isinstance(block, dict):
                blocks.append(block)
            else:
                other[str(pattern)] = block
    for block in blocks:
        parsed.approvers += [n for n in _names(block.get("approvers")) if n not in parsed.approvers]
        parsed.reviewers += [n for n in _names(block.get("reviewers")) if n not in parsed.reviewers]
        parsed.emeritus += [n for n in _names(block.get("emeritus_approvers")) if n not in parsed.emeritus]
    parsed.labels = [str(x) for x in data.get("labels") or [] if isinstance(x, str)]
    options = data.get("options")
    parsed.no_parent_owners = bool(isinstance(options, dict) and options.get("no_parent_owners"))
    if other:
        parsed.filters_raw = yaml.safe_dump(other, sort_keys=True)
    return parsed


def parse_aliases(text: str) -> dict[str, list[str]]:
    """alias name (as written) -> member logins, lower-cased, in file order."""
    data = yaml.safe_load(text) or {}
    raw = data.get("aliases") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {str(name): _names(members) for name, members in raw.items()}


_KK_RAW = re.compile(r"^https://raw\.githubusercontent\.com/kubernetes/kubernetes/[^/]+/(.+)$")
MAX_NEW_FETCHES = 400
MAX_IN_FLIGHT = 4  # concurrent contents-API requests
Origin = tuple[str, str]  # (graph label, key) of the SIG or Subproject a directory was derived from


@dataclass
class Selection:
    paths: dict[str, str]  # OWNERS path -> blob sha
    origins: dict[str, list[Origin]]  # OWNERS path -> SIG / Subproject it was derived from
    seed_dirs: dict[str, int] = field(default_factory=dict)  # sig dir -> directories from sigs.yaml (step 1)
    labelled_dirs: dict[str, int] = field(default_factory=dict)  # sig dir -> directories from `labels:` (step 2)
    fetches: int = 0  # network requests the selection needed (cache misses)


def _directory_of(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return "" if parent == "." else parent


def seed_directories(chart: OrgChart, scope: set[str]) -> dict[str, list[tuple[str, str]]]:
    """Step 1: kubernetes/kubernetes directory -> [(sig dir, subproject key)] from in-scope `owners:` URLs."""
    seeds: dict[str, list[tuple[str, str]]] = {}
    for sp in chart.subprojects:
        if sp["sig_dir"] not in scope:
            continue
        for url in sp.get("owners_urls") or []:
            m = _KK_RAW.match(url)
            if m:
                owner = (sp["sig_dir"], sp["key"])
                found = seeds.setdefault(_directory_of(m.group(1)), [])
                if owner not in found:
                    found.append(owner)
    return seeds


def _region_prefix(directory: str) -> str:
    parts = directory.split("/")
    return "/".join(parts[: 4 if parts[0] == "staging" else 2])


def _under(directory: str, root: str) -> bool:
    return root == "" or directory == root or directory.startswith(root + "/")


def select_owners(
    tree: list[dict[str, Any]],
    chart: OrgChart,
    scope: set[str],
    read: Callable[[str], str],
    is_cached: Callable[[str], bool] = lambda _p: True,
    prefetch: Callable[[list[str]], None] | None = None,
) -> Selection:
    """OWNERS files of the in-scope SIGs, derived from public data only.

    1. Directories named by `owners:` URLs of the SIGs' subprojects in sigs.yaml, and everything below them.
    2. Any OWNERS file in the same part of the tree (within three path components of a step 1 directory) whose own
       `labels:` carries `sig/<scope sig>`.
    Ancestors of the selected directories are added without an origin so inheritance resolves.
    """
    all_owners = {
        e["path"]: e["sha"] for e in tree if e.get("type") == "blob" and PurePosixPath(e["path"]).name == "OWNERS"
    }
    seeds = seed_directories(chart, scope)
    origins: dict[str, list[Origin]] = {}
    chosen: dict[str, str] = {}
    seed_counts: dict[str, set[str]] = {}
    for path, sha in all_owners.items():
        directory = _directory_of(path)
        owners = [o for root, found in seeds.items() if _under(directory, root) and root != "" for o in found]
        if owners:
            chosen[path] = sha
            for sig, key in owners:
                if ("Subproject", key) not in origins.setdefault(path, []):
                    origins[path].append(("Subproject", key))
                seed_counts.setdefault(sig, set()).add(path)
    regions = {_region_prefix(d) for d in seeds if d}
    candidates = [p for p in all_owners if p not in chosen and any(_under(_directory_of(p), r) for r in regions)]
    misses = [p for p in candidates if not is_cached(p)]
    if len(misses) > MAX_NEW_FETCHES:
        raise RuntimeError(f"OWNERS label scan needs {len(misses)} new requests (limit {MAX_NEW_FETCHES})")
    if prefetch is not None and misses:
        prefetch(misses)
    label_counts: dict[str, set[str]] = {}
    for path in candidates:
        labels = parse_owners(path, all_owners[path], read(path)).labels
        sigs = [f"sig-{x[4:]}" for x in labels if x.startswith("sig/") and f"sig-{x[4:]}" in scope]
        if sigs:
            chosen[path] = all_owners[path]
            origins[path] = [("SIG", s) for s in sigs]
            for s in sigs:
                label_counts.setdefault(s, set()).add(path)
    ancestors = {""}
    for path in chosen:
        parts = _directory_of(path).split("/")
        ancestors.update("/".join(parts[:i]) for i in range(1, len(parts)))
    for path, sha in all_owners.items():
        if _directory_of(path) in ancestors:
            chosen.setdefault(path, sha)
    return Selection(
        paths=dict(sorted(chosen.items())),
        origins=origins,
        seed_dirs={k: len(v) for k, v in seed_counts.items()},
        labelled_dirs={k: len(v) for k, v in label_counts.items()},
        fetches=len(misses),
    )


def load_chart(settings: Settings, community_sha: str | None = None) -> OrgChart:
    """Parse sigs.yaml of the community clone at `community_sha` (default: resolve it, fetching the clone)."""
    sha = community_sha or ensure_repo(settings, "community")
    git = Git(clone_path(settings, "community"))
    try:
        text = git.read(sha, SIGS_PATH)
    finally:
        git.close()
    if text is None:
        raise FileNotFoundError(f"{SIGS_PATH} missing at {sha}")
    return parse_sigs_yaml(text, sha, set(settings.sig_list))


class OwnersSource:
    """Contents-API reader with a disk cache keyed by blob SHA, so a later commit refetches only changed files."""

    def __init__(self, settings: Settings, sha: str | None = None) -> None:
        self.sha = sha or ensure_repo(settings, "owners")
        self.cache = Path(settings.repo_cache_dir) / "owners" / self.sha
        self.cache.mkdir(parents=True, exist_ok=True)
        self.blob_cache = self.cache.parent / "blobs"
        self.blob_cache.mkdir(parents=True, exist_ok=True)
        self._blobs: dict[str, str] = {}  # path -> git blob sha at this commit, from the tree
        self._token = resolve_token(settings)
        self._http = httpx.Client(headers=self._headers("application/vnd.github.raw+json"), timeout=60)
        self._pause_until = 0.0  # a rate-limit wait observed by any request holds all of them
        self._lock = threading.Lock()
        self.requests = 0

    def _headers(self, accept: str) -> dict[str, str]:
        return {"Authorization": f"bearer {self._token}", "Accept": accept, "User-Agent": "kep-brain-worker"}

    def close(self) -> None:
        self._http.close()

    def _get(self, url: str, accept: str) -> httpx.Response:
        for attempt in range(6):
            time.sleep(max(0.0, self._pause_until - time.monotonic()))
            resp = self._http.get(url, headers=self._headers(accept))
            with self._lock:
                self.requests += 1
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                wait = min(float(resp.headers.get("retry-after", 2 ** (attempt + 1))), 60.0)
                log.warning("owners_fetch_retry", url=url, status=resp.status_code, wait=wait)
                with self._lock:
                    self._pause_until = max(self._pause_until, time.monotonic() + wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def tree(self) -> list[dict[str, Any]]:
        cached = self.cache / "_tree.json"
        if cached.exists():
            tree: list[dict[str, Any]] = json.loads(cached.read_text(encoding="utf-8"))
            self._blobs = {e["path"]: e["sha"] for e in tree}
            return tree
        resp = self._get(f"{API}/repos/{KK_REPO}/git/trees/{self.sha}?recursive=1", "application/vnd.github+json")
        payload = resp.json()
        if payload.get("truncated"):
            raise RuntimeError(f"{KK_REPO}@{self.sha} tree is truncated")
        tree = [{"path": e["path"], "type": e["type"], "sha": e["sha"]} for e in payload["tree"]]
        cached.write_text(json.dumps(tree), encoding="utf-8")
        self._blobs = {e["path"]: e["sha"] for e in tree}
        return tree

    def _file(self, path: str) -> Path:
        blob = self._blobs.get(path)
        return self.blob_cache / blob if blob else self.cache / path.replace("/", "__")

    def is_cached(self, path: str) -> bool:
        return self._file(path).exists()

    def prefetch(self, paths: Iterable[str]) -> None:
        """Fill the disk cache for `paths` with up to MAX_IN_FLIGHT concurrent requests."""
        todo = [p for p in dict.fromkeys(paths) if not self.is_cached(p)]
        if len(todo) < 2:
            return
        with ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT) as pool:
            list(pool.map(self.read, todo))

    def read(self, path: str) -> str:
        cached = self._file(path)
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        resp = self._get(
            f"{API}/repos/{KK_REPO}/contents/{quote(path)}?ref={self.sha}", "application/vnd.github.raw+json"
        )
        cached.write_text(resp.text, encoding="utf-8")
        return resp.text


def _doc_row(f: OwnersFile, sha: str) -> dict[str, Any]:
    url = blob_url(KK_REPO, sha, f.path)
    return {
        "key": f"{KK_REPO}:{f.path}",
        "kind": "owners",
        "repo": KK_REPO,
        "path": f.path,
        "directory": f.directory,
        "title": f.path,
        "blob_sha": f.blob_sha,
        "url": url,
        "source_url": url,
        "source_sha": sha,
        "byte_size": len(f.text.encode("utf-8")),
        "raw_hash": hashlib.sha256(f.text.encode("utf-8")).hexdigest(),
        "labels_applied": f.labels or None,
        "no_parent_owners": f.no_parent_owners,
        "has_filters": f.filters_raw is not None,
        "filters_raw": f.filters_raw,
    }


def sync_owners(
    writer: BatchWriter,
    settings: Settings,
    source: OwnersSource | None = None,
    chart: OrgChart | None = None,
    community_sha: str | None = None,
) -> dict[str, int]:
    own = source is None
    src = source or OwnersSource(settings)
    try:
        return _sync(writer, src, chart or load_chart(settings, community_sha), set(settings.sig_list))
    finally:
        if own:
            src.close()


def _sync(writer: BatchWriter, src: OwnersSource, chart: OrgChart, scope: set[str]) -> dict[str, int]:
    sha = src.sha
    selection = select_owners(src.tree(), chart, scope, src.read, src.is_cached, lambda paths: src.prefetch(paths))
    log.info(
        "owners_selected",
        files=len(selection.paths),
        fetches=selection.fetches,
        seeds=selection.seed_dirs,
        labelled=selection.labelled_dirs,
    )
    selected = selection.paths
    src.prefetch([*selected, ALIASES_PATH])
    files = [parse_owners(path, blob, src.read(path)) for path, blob in selected.items()]
    aliases_text = src.read(ALIASES_PATH)
    aliases = parse_aliases(aliases_text)
    alias_by_lower = {name.lower(): name for name in aliases}
    aliases_url = blob_url(KK_REPO, sha, ALIASES_PATH)

    used_aliases: dict[str, str] = {}  # lower-case name -> alias name as written
    logins: dict[str, None] = {}
    for f in files:
        for name in f.approvers + f.reviewers + f.emeritus:
            if name in alias_by_lower:
                used_aliases[name] = alias_by_lower[name]
            elif (login := normalise_login(name)) is not None:
                logins[login] = None
    for name in used_aliases.values():
        for member in aliases[name]:
            login = normalise_login(member)
            if login:
                logins[login] = None

    existing = {
        row[0] for row in writer.query("MATCH (p:Person) WHERE p.key IN $keys RETURN p.key", {"keys": list(logins)})
    }
    writer.upsert_nodes(
        "Person",
        [
            {
                "key": login,
                "login": login,
                "login_raw": login,
                "url": person_url(login),
                "is_bot": is_bot(login),
                "source_url": aliases_url,
            }
            for login in logins
            if login not in existing
        ],
    )
    writer.upsert_nodes(
        "Document",
        [
            {
                "key": f"{KK_REPO}:{ALIASES_PATH}",
                "kind": "owners_aliases",
                "repo": KK_REPO,
                "path": ALIASES_PATH,
                "title": ALIASES_PATH,
                "url": aliases_url,
                "source_url": aliases_url,
                "source_sha": sha,
                "byte_size": len(aliases_text.encode("utf-8")),
                "raw_hash": hashlib.sha256(aliases_text.encode("utf-8")).hexdigest(),
            }
        ],
    )
    writer.upsert_nodes("Document", [_doc_row(f, sha) for f in files], extra_labels=["OwnersFile"])
    writer.upsert_nodes(
        "Alias",
        [
            {
                "key": f"{KK_REPO}:{name}",
                "name": name,
                "repo": KK_REPO,
                "member_count": len(aliases[name]),
                "url": aliases_url,
                "source_url": aliases_url,
                "source_sha": sha,
            }
            for name in used_aliases.values()
        ],
    )

    t = writer.observed_at
    member_rows = [
        {
            "from": login,
            "to": f"{KK_REPO}:{name}",
            "props": {**open_state_props(t, aliases_url, "first_observed"), "position": pos, "w": 1},
        }
        for name in used_aliases.values()
        for pos, login in enumerate(filter(None, map(normalise_login, aliases[name])))
    ]
    writer.merge_open_edges("MEMBER_OF", "Person", "Alias", member_rows)
    writer.query(
        "UNWIND $rows AS r MATCH (a:Alias {key: r.key})<-[e:MEMBER_OF]-(p:Person) "
        "WHERE e.valid_to = $open AND NOT p.key IN r.current SET e.valid_to = $at, e.valid_to_iso = $at_iso",
        {
            "rows": [
                {"key": f"{KK_REPO}:{n}", "current": [x for x in map(normalise_login, aliases[n]) if x]}
                for n in used_aliases.values()
            ],
            "open": VALID_TO_OPEN,
            "at": t,
            "at_iso": iso(t),
        },
    )

    def target(name: str) -> tuple[str, str] | None:
        if name in alias_by_lower:
            return "Alias", f"{KK_REPO}:{alias_by_lower[name]}"
        login = normalise_login(name)
        return ("Person", login) if login else None

    counts = {"APPROVER": 0, "REVIEWER": 0, "EMERITUS_APPROVER": 0}
    for rel, attr in (("APPROVER", "approvers"), ("REVIEWER", "reviewers"), ("EMERITUS_APPROVER", "emeritus")):
        by_label: dict[str, list[dict[str, Any]]] = {"Person": [], "Alias": []}
        current: dict[str, list[str]] = {}
        for f in files:
            doc_key = f"{KK_REPO}:{f.path}"
            current[doc_key] = []
            props = {**open_state_props(t, blob_url(KK_REPO, sha, f.path), "first_observed"), "w": 1}
            for name in getattr(f, attr):
                resolved = target(name)
                if resolved is None:
                    continue
                label, key = resolved
                current[doc_key].append(key)
                by_label[label].append({"from": doc_key, "to": key, "props": props})
        writer.close_absent_edges(rel, "Document", None, current)
        for label, rows in by_label.items():
            writer.merge_open_edges(rel, "Document", label, rows)
            counts[rel] += len(rows)

    sig_rows: list[dict[str, Any]] = []
    sig_current: dict[str, list[str]] = {}
    for f in files:
        doc_key = f"{KK_REPO}:{f.path}"
        sig_current[doc_key] = []
        props = {**open_state_props(t, blob_url(KK_REPO, sha, f.path), "first_observed"), "w": 4}
        for label in f.labels:
            if label.startswith("sig/"):
                sig_current[doc_key].append("sig-" + label[4:])
                sig_rows.append({"from": doc_key, "to": "sig-" + label[4:], "props": props})
    writer.close_absent_edges("APPLIES_LABEL", "Document", None, sig_current)
    writer.merge_open_edges("APPLIES_LABEL", "Document", "SIG", sig_rows)

    component_rows: dict[str, list[dict[str, Any]]] = {"SIG": [], "Subproject": []}
    component_current: dict[str, dict[str, list[str]]] = {
        "SIG": {k: [] for k in scope},
        "Subproject": {sp["key"]: [] for sp in chart.subprojects if sp["sig_dir"] in scope},
    }
    for path, origin_list in selection.origins.items():
        props = {**open_state_props(t, blob_url(KK_REPO, sha, path), "first_observed"), "w": 4}
        for label, key in origin_list:
            component_rows[label].append({"from": key, "to": f"{KK_REPO}:{path}", "props": props})
            component_current[label].setdefault(key, []).append(f"{KK_REPO}:{path}")
    for label, rows in component_rows.items():
        writer.close_absent_edges("COMPONENT_DIR", label, None, component_current[label])
        writer.merge_open_edges("COMPONENT_DIR", label, "Document", rows)

    by_dir = {f.directory: f for f in files}
    parent_rows: list[dict[str, Any]] = []
    for f in files:
        if f.directory == "":
            continue
        parts = f.directory.split("/")
        parent = next(
            (by_dir["/".join(parts[:i])] for i in range(len(parts) - 1, -1, -1) if "/".join(parts[:i]) in by_dir), None
        )
        if parent is None:
            continue
        parent_rows.append(
            {
                "from": f"{KK_REPO}:{f.path}",
                "to": f"{KK_REPO}:{parent.path}",
                "props": {"inherits": not f.no_parent_owners, "source_url": blob_url(KK_REPO, sha, f.path), "w": 1},
            }
        )
    writer.upsert_edges("PARENT_OWNERS", "Document", "Document", parent_rows)

    result = {
        "owners_files": len(files),
        "aliases": len(used_aliases),
        "people": len(logins),
        "member_of": len(member_rows),
        "applies_label": len(sig_rows),
        "parent_owners": len(parent_rows),
        "component_dir": sum(len(r) for r in component_rows.values()),
        **{k.lower(): v for k, v in counts.items()},
    }
    log.info("owners_loaded", sha=sha, **result)
    return result
