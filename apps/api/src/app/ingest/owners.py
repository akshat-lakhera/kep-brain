"""OWNERS layer: OWNERS files of the directories the three SIGs maintain plus the root `OWNERS_ALIASES` (03 §4.1, §5.1).

Files come from the GitHub contents API at a pinned `kubernetes/kubernetes` commit (ADR 0007: no clone of
that repository) and are cached under `<REPO_CACHE_DIR>/owners/<sha>/`. Ownership is a snapshot source, so
every state edge starts at first observation (`valid_from_basis = first_observed`) and a later sync closes
the edges the file no longer lists (03 §7.6).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx
import structlog
import yaml

from app.db.batch import BatchWriter
from app.ingest.common import blob_url, is_bot, iso, normalise_login, open_state_props, person_url
from app.ingest.github import resolve_token
from app.schema.labels import VALID_TO_OPEN
from app.settings import Settings

log = structlog.get_logger(__name__)

KK_REPO = "kubernetes/kubernetes"
# kubernetes/kubernetes master on 2026-10-14; the OWNERS layer never moves unless this is changed.
KK_PIN_SHA = "2fb87b41a29b74e95c06b70fb61ba318fb580bf3"
ALIASES_PATH = "OWNERS_ALIASES"
API = "https://api.github.com"

# Component -> source directories (03 §5.1 `COMPONENT_DIR`): the code and tests the three SIGs maintain.
COMPONENT_DIRECTORIES: dict[str, tuple[str, ...]] = {
    "kubelet": (
        "pkg/kubelet",
        "cmd/kubelet",
        "staging/src/k8s.io/kubelet",
        "staging/src/k8s.io/cri-api",
        "test/e2e_node",
        "test/e2e/node",
    ),
    "kube-scheduler": (
        "pkg/scheduler",
        "cmd/kube-scheduler",
        "staging/src/k8s.io/kube-scheduler",
        "test/e2e/scheduling",
        "test/integration/scheduler",
        "test/integration/scheduler_perf",
    ),
    "kube-controller-manager": (
        "pkg/controller",
        "cmd/kube-controller-manager",
        "staging/src/k8s.io/kube-controller-manager",
        "staging/src/k8s.io/controller-manager",
        "pkg/apis/apps",
        "pkg/apis/batch",
        "pkg/registry/apps",
        "pkg/registry/batch",
        "test/e2e/apps",
    ),
}


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
        if isinstance(item, str) and item.strip():
            seen.setdefault(item.strip().lstrip("@").lower(), None)
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


def wanted_directory(directory: str) -> bool:
    return any(directory == p or directory.startswith(p + "/") for dirs in COMPONENT_DIRECTORIES.values() for p in dirs)


def select_owner_paths(tree: list[dict[str, Any]]) -> dict[str, str]:
    """OWNERS path -> blob sha for every wanted directory and every ancestor of one (so inheritance resolves)."""
    all_owners = {
        e["path"]: e["sha"] for e in tree if e.get("type") == "blob" and PurePosixPath(e["path"]).name == "OWNERS"
    }
    ancestors = {""}
    for dirs in COMPONENT_DIRECTORIES.values():
        for d in dirs:
            parts = d.split("/")
            ancestors.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    chosen: dict[str, str] = {}
    for path, sha in all_owners.items():
        parent = str(PurePosixPath(path).parent)
        directory = "" if parent == "." else parent
        if directory in ancestors or wanted_directory(directory):
            chosen[path] = sha
    return dict(sorted(chosen.items()))


class OwnersSource:
    """Contents-API reader with a per-commit disk cache."""

    def __init__(self, settings: Settings, sha: str = KK_PIN_SHA) -> None:
        self.sha = sha
        self.cache = Path(settings.repo_cache_dir) / "owners" / sha
        self.cache.mkdir(parents=True, exist_ok=True)
        self._token = resolve_token(settings)
        self._http = httpx.Client(headers=self._headers("application/vnd.github.raw+json"), timeout=60)

    def _headers(self, accept: str) -> dict[str, str]:
        return {"Authorization": f"bearer {self._token}", "Accept": accept, "User-Agent": "kep-brain-worker"}

    def close(self) -> None:
        self._http.close()

    def _get(self, url: str, accept: str) -> httpx.Response:
        for attempt in range(6):
            resp = self._http.get(url, headers=self._headers(accept))
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                wait = float(resp.headers.get("retry-after", 2 ** (attempt + 1)))
                log.warning("owners_fetch_retry", url=url, status=resp.status_code, wait=wait)
                time.sleep(min(wait, 60))
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def tree(self) -> list[dict[str, Any]]:
        cached = self.cache / "_tree.json"
        if cached.exists():
            tree: list[dict[str, Any]] = json.loads(cached.read_text(encoding="utf-8"))
            return tree
        resp = self._get(f"{API}/repos/{KK_REPO}/git/trees/{self.sha}?recursive=1", "application/vnd.github+json")
        payload = resp.json()
        if payload.get("truncated"):
            raise RuntimeError(f"{KK_REPO}@{self.sha} tree is truncated")
        tree = [{"path": e["path"], "type": e["type"], "sha": e["sha"]} for e in payload["tree"]]
        cached.write_text(json.dumps(tree), encoding="utf-8")
        return tree

    def read(self, path: str) -> str:
        cached = self.cache / path.replace("/", "__")
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


def _merge_open(writer: BatchWriter, rel: str, from_label: str, to_label: str, rows: list[dict[str, Any]]) -> None:
    for i in range(0, len(rows), 500):
        writer.query(
            f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.from}}) MATCH (b:{to_label} {{key: r.to}}) "
            f"MERGE (a)-[e:{rel} {{valid_to: $open}}]->(b) "
            "ON CREATE SET e += r.props, e.observed_at = $now, e.sync_run_id = $run "
            "ON MATCH SET e.observed_at = $now, e.sync_run_id = $run",
            {"rows": rows[i : i + 500], "open": VALID_TO_OPEN, "now": writer.observed_at, "run": writer.sync_run_id},
        )


def _close_absent(writer: BatchWriter, rel: str, from_label: str, current: dict[str, list[str]]) -> None:
    rows = [{"key": k, "current": v} for k, v in current.items()]
    for i in range(0, len(rows), 500):
        writer.query(
            f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.key}})-[e:{rel}]->(b) "
            "WHERE e.valid_to = $open AND NOT b.key IN r.current SET e.valid_to = $at, e.valid_to_iso = $at_iso",
            {
                "rows": rows[i : i + 500],
                "open": VALID_TO_OPEN,
                "at": writer.observed_at,
                "at_iso": iso(writer.observed_at),
            },
        )


def sync_owners(writer: BatchWriter, settings: Settings, source: OwnersSource | None = None) -> dict[str, int]:
    own = source is None
    src = source or OwnersSource(settings)
    try:
        return _sync(writer, src)
    finally:
        if own:
            src.close()


def _sync(writer: BatchWriter, src: OwnersSource) -> dict[str, int]:
    sha = src.sha
    selected = select_owner_paths(src.tree())
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
    _merge_open(writer, "MEMBER_OF", "Person", "Alias", member_rows)
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
        _close_absent(writer, rel, "Document", current)
        for label, rows in by_label.items():
            _merge_open(writer, rel, "Document", label, rows)
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
    _close_absent(writer, "APPLIES_LABEL", "Document", sig_current)
    _merge_open(writer, "APPLIES_LABEL", "Document", "SIG", sig_rows)

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
        **{k.lower(): v for k, v in counts.items()},
    }
    log.info("owners_loaded", sha=sha, **result)
    return result
