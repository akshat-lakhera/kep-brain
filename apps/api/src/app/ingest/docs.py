"""Doc layer: KEPs, documents, sections, people, gates, releases and metadata edges (03 §4.2–§4.3, §5.2–§5.3).

Source: the `kubernetes/enhancements` clone at the pinned SHA. State edges get
their validity from a replay of every `kep.yaml` / PRR revision, oldest first
(03 §7.6): `valid_from` is the author date of the commit that introduced the
value, `valid_to` the commit that removed it, or the open sentinel.

`build_corpus` reads everything once; `sync_docs` writes the doc layer and
`app.ingest.history.sync_history` writes commits and status changes from the
same corpus.
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog

from app.db.batch import BatchWriter
from app.ingest.common import (
    ENHANCEMENTS_REPO,
    Git,
    Revision,
    blob_url,
    file_revisions,
    is_bot,
    iso,
    normalise_login,
    path_weight,
    person_url,
    state_props,
    tree_url,
)
from app.ingest.kep_yaml import MILESTONE_STAGES, KepMeta, load_yaml, parse_kep_yaml, release_minor
from app.ingest.repos import clone_path, ensure_repo
from app.ingest.sections import ParsedSection, split_sections, summary_text
from app.ingest.sigs import OrgChart, sync_sigs
from app.schema.labels import VALID_TO_OPEN
from app.settings import Settings

log = structlog.get_logger(__name__)
REF_PLACEHOLDERS = {"", "n/a", "na", "none", "tbd", "-", "todo", "null"}
PRR_STAGES = ("alpha", "beta", "stable")
GITHUB_ENH_RE = re.compile(r"^https?://github\.com/kubernetes/enhancements/(?:tree|blob)/[^/]+/(keps/.+)$", re.I)
NUMBER_RE = re.compile(r"^(?:kep-?|#)?\s*(\d{1,5})$", re.I)
REPLAYED_RELS = frozenset(
    {"OWNED_BY", "PARTICIPATES", "AUTHORED", "REVIEWS", "APPROVES", "EDITS", "PRR_APPROVED", "REPLACES",
     "SUPERSEDED_BY", "SEE_ALSO", "REFERS_TO", "GATED_BY", "TARGETS", "LATEST"}
)  # fmt: skip
KK_RELEASES_URL = "https://api.github.com/repos/kubernetes/kubernetes/releases"
RELEASES_CACHE_SECONDS = 24 * 3600


# --------------------------------------------------------------------------- corpus


@dataclass
class ParsedRevision:
    rev: Revision
    meta: KepMeta


@dataclass
class PrrRevision:
    rev: Revision
    approvers: dict[str, str]  # stage -> login


@dataclass
class KepSource:
    key: str  # keps/<sig>/<dir>
    sig_dir: str
    dir_name: str
    stub: bool
    head: KepMeta
    revisions: list[ParsedRevision] = field(default_factory=list)
    prr_path: str | None = None
    prr_revisions: list[PrrRevision] = field(default_factory=list)
    readme_text: str | None = None
    sections: list[ParsedSection] = field(default_factory=list)

    @property
    def yaml_path(self) -> str:
        return f"{self.key}/kep.yaml"

    @property
    def readme_path(self) -> str:
        return f"{self.key}/README.md"


@dataclass
class Corpus:
    git: Git
    sha: str
    sha_time: int
    community_git: Git
    community_sha: str
    in_scope_sigs: list[str]
    keps: dict[str, KepSource]
    tree: dict[str, tuple[str, str]]
    dir_updated: dict[str, tuple[str, int]]  # path -> (last commit sha, at) for loaded files and dirs
    resolver: RefResolver


class RefResolver:
    """Resolves `see-also` / `replaces` / `superseded-by` strings (recon Q8).

    Order: KEP directory path -> old filename via git renames or symlink -> bare number -> external URL.
    """

    def __init__(self, kep_dirs: Iterable[str], numbers: dict[int, list[str]], renames: dict[str, str]) -> None:
        self.kep_dirs = set(kep_dirs)
        self.numbers = numbers
        self.renames = renames

    def _dir_of(self, path: str) -> str | None:
        path = path.strip().strip("/")
        for suffix in ("/README.md", "/kep.yaml", "/readme.md"):
            if path.endswith(suffix):
                path = path[: -len(suffix)]
        if not path.startswith("keps/"):
            path = "keps/" + path if path.startswith("sig-") else path
        if path in self.kep_dirs:
            return path
        seen: set[str] = set()
        candidates = [path, f"{path}/README.md", f"{path}/kep.yaml"]
        for cand in candidates:
            current = cand
            while current in self.renames and current not in seen:
                seen.add(current)
                current = self.renames[current]
            if current != cand:
                target = current.rsplit("/", 1)[0] if current.endswith((".md", ".yaml")) else current
                if target in self.kep_dirs:
                    return target
        last = path.rsplit("/", 1)[-1]
        m = re.match(r"^(\d+)(?:-|$)", last)
        if m and path.count("/") == 2:
            # `keps/<sig>/<number>[-slug]` naming a directory that does not exist: same number in
            # the same SIG first, then a repository-wide unique number (KEPs moved between SIGs).
            sig = path.split("/")[1]
            all_hits = self.numbers.get(int(m.group(1)), [])
            hits = [k for k in all_hits if k.split("/")[1] == sig] or all_hits
            if len(hits) == 1:
                return hits[0]
        return None

    def resolve(self, raw: str, from_key: str) -> tuple[str, str] | None:
        """('kep', key) | ('external', url) | None when unresolvable or a placeholder."""
        text = raw.strip().strip("'\"").strip()
        if text.lower() in REF_PLACEHOLDERS:
            return None
        gh = GITHUB_ENH_RE.match(text.split("#", 1)[0])
        if gh:
            target = self._dir_of(gh.group(1))
            return ("kep", target) if target else ("external", text)
        if re.match(r"^https?://", text, re.I):
            return ("external", text)
        if re.match(r"^\d+-[\w.-]+$", text):
            named = [d for d in self.kep_dirs if d.rsplit("/", 1)[-1] == text]
            if len(named) == 1:
                return ("kep", named[0])
            text = text.split("-", 1)[0]
        m = NUMBER_RE.match(text)
        if m:
            hits = self.numbers.get(int(m.group(1)), [])
            if len(hits) > 1:
                hits = [h for h in hits if h.split("/")[1] == from_key.split("/")[1]] or hits
            return ("kep", hits[0]) if len(hits) == 1 else None
        if text.startswith("kubernetes/enhancements/"):
            text = text[len("kubernetes/enhancements/") :]
        if "/" in text:
            target = self._dir_of(text)
            return ("kep", target) if target else None
        return None


def _rename_map(git: Git, sha: str) -> dict[str, str]:
    out = git.run("log", "--diff-filter=R", "-M", "--name-status", "--format=", sha, "--", "keps")
    renames: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            renames.setdefault(parts[1], parts[2])
    return renames


def _last_touch(git: Git, sha: str, paths: list[str]) -> dict[str, tuple[str, int]]:
    """Newest commit touching each file under `paths`, plus each KEP directory."""
    out = git.run("log", "--name-only", "--format=@@%H %at", sha, "--", *paths)
    result: dict[str, tuple[str, int]] = {}
    current: tuple[str, int] | None = None
    for line in out.splitlines():
        if line.startswith("@@"):
            c_sha, at = line[2:].split()
            current = (c_sha, int(at))
        elif line.strip() and current is not None:
            path = line.strip()
            result.setdefault(path, current)
            parts = path.split("/")
            if len(parts) >= 4:
                result.setdefault("/".join(parts[:3]), current)
    return result


def _parse_prr(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    try:
        data = load_yaml(text)
    except Exception:  # noqa: BLE001 - a broken PRR revision carries no approvals
        return {}
    approvers: dict[str, str] = {}
    if isinstance(data, dict):
        for stage in PRR_STAGES:
            entry = data.get(stage)
            login = normalise_login(entry.get("approver")) if isinstance(entry, dict) else None
            if login:
                approvers[stage] = login
    return approvers


def build_corpus(settings: Settings, shas: tuple[str, str] | None = None) -> Corpus:
    """Read the pinned commits into memory. `shas` = (enhancements, community) when the caller already resolved them."""
    started = time.monotonic()
    sha = shas[0] if shas else ensure_repo(settings, "enhancements")
    git = Git(clone_path(settings, "enhancements"))
    community_sha = shas[1] if shas else ensure_repo(settings, "community")
    community_git = Git(clone_path(settings, "community"))
    tree = git.ls_tree(sha, "keps")
    kep_dirs = sorted(p[: -len("/kep.yaml")] for p in tree if p.endswith("/kep.yaml"))
    scope = settings.sig_list
    in_scope = [d for d in kep_dirs if d.split("/")[1] in scope]

    heads: dict[str, KepMeta] = {}
    numbers: dict[int, list[str]] = defaultdict(list)
    for d in kep_dirs:
        meta = parse_kep_yaml(git.read(sha, f"{d}/kep.yaml") or "", d.split("/")[1])
        heads[d] = meta
        if meta.number is not None:
            numbers[meta.number].append(d)
    resolver = RefResolver(kep_dirs, dict(numbers), _rename_map(git, sha))

    keps: dict[str, KepSource] = {}
    for d in in_scope:
        keps[d] = KepSource(key=d, sig_dir=d.split("/")[1], dir_name=d.split("/", 2)[2], stub=False, head=heads[d])
    # stubs: KEPs outside the loaded SIGs that a loaded KEP names
    for d in in_scope:
        meta = heads[d]
        for raw in meta.see_also_raw + meta.replaces_raw + meta.superseded_by_raw:
            hit = resolver.resolve(raw, d)
            if hit and hit[0] == "kep" and hit[1] not in keps:
                t = hit[1]
                keps[t] = KepSource(
                    key=t, sig_dir=t.split("/")[1], dir_name=t.split("/", 2)[2], stub=True, head=heads[t]
                )

    for src in keps.values():
        if src.head.number is not None:
            for sig in (src.sig_dir, src.head.owning_sig or ""):
                cand = f"keps/prod-readiness/{sig}/{src.head.number}.yaml"
                if cand in tree:
                    src.prr_path = cand
                    break

    def walk(src: KepSource) -> tuple[KepSource, list[Revision], list[Revision]]:
        revs = file_revisions(git, sha, src.yaml_path)
        prr = file_revisions(git, sha, src.prr_path) if src.prr_path and not src.stub else []
        return src, revs, prr

    with ThreadPoolExecutor(max_workers=8) as pool:
        walked = list(pool.map(walk, keps.values()))
    for src, revs, prr in walked:
        for rev in revs:
            text = git.read(rev.sha, rev.path)
            if text is None:
                continue
            meta = parse_kep_yaml(text, src.sig_dir)
            if meta.parse_error is None:
                src.revisions.append(ParsedRevision(rev=rev, meta=meta))
        for rev in prr:
            src.prr_revisions.append(PrrRevision(rev=rev, approvers=_parse_prr(git.read(rev.sha, rev.path))))
        if not src.stub:
            src.readme_text = git.read(sha, src.readme_path)
            if src.readme_text:
                src.sections = split_sections(src.readme_text)

    paths = sorted({f"keps/{s}" for s in scope} | {"keps/prod-readiness"})
    dir_updated = _last_touch(git, sha, paths)
    for src in keps.values():
        if src.stub and src.key not in dir_updated:
            dir_updated.update(_last_touch(git, sha, [src.key]))
    corpus = Corpus(
        git=git,
        sha=sha,
        sha_time=git.commit_time(sha),
        community_git=community_git,
        community_sha=community_sha,
        in_scope_sigs=scope,
        keps=keps,
        tree=tree,
        dir_updated=dir_updated,
        resolver=resolver,
    )
    log.info(
        "corpus_built",
        keps=sum(not k.stub for k in keps.values()),
        stubs=sum(k.stub for k in keps.values()),
        revisions=sum(len(k.revisions) for k in keps.values()),
        seconds=round(time.monotonic() - started, 1),
    )
    return corpus


# --------------------------------------------------------------------------- releases


def fetch_release_dates(settings: Settings, cutoff: int) -> dict[str, int]:
    """`v1.NN` -> published_at of the first non-prerelease `v1.NN.0` at or before `cutoff`.

    Source: GitHub releases of kubernetes/kubernetes; cached in REPO_CACHE_DIR so a
    pinned build is reproducible offline.
    """
    cache_file = Path(settings.repo_cache_dir) / "kubernetes-releases.json"
    releases: list[dict[str, Any]]
    # Re-read the cache for a day, then refetch: a scheduled worker must notice a newly shipped release.
    fresh = cache_file.exists() and time.time() - cache_file.stat().st_mtime < RELEASES_CACHE_SECONDS
    if fresh:
        releases = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"
        releases = []
        with httpx.Client(timeout=30, headers=headers) as client:
            for page in range(1, 20):
                resp = client.get(KK_RELEASES_URL, params={"per_page": 100, "page": page})
                resp.raise_for_status()
                batch = resp.json()
                if not batch:
                    break
                releases.extend(
                    {"tag_name": r["tag_name"], "published_at": r["published_at"], "prerelease": r["prerelease"]}
                    for r in batch
                )
        cache_file.write_text(json.dumps(releases), encoding="utf-8")
    from datetime import datetime

    dates: dict[str, int] = {}
    for r in releases:
        m = re.match(r"^v1\.(\d+)\.0$", r.get("tag_name") or "")
        if not m or r.get("prerelease") or not r.get("published_at"):
            continue
        at = int(datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")).timestamp())
        if at <= cutoff:
            key = f"v1.{int(m.group(1))}"
            dates[key] = min(at, dates.get(key, at))
    return dates


# --------------------------------------------------------------------------- edge specs and intervals

EdgeSpec = tuple[str, str, str, str, str, tuple[tuple[str, Any], ...]]  # rel, from_label, from, to_label, to, ident


@dataclass
class Interval:
    spec: EdgeSpec
    props: dict[str, Any]
    valid_from: int
    valid_to: int
    source_url: str


def _meta_specs(
    src: KepSource, meta: KepMeta, chart: OrgChart, resolver: RefResolver
) -> dict[EdgeSpec, dict[str, Any]]:
    k = src.key
    specs: dict[EdgeSpec, dict[str, Any]] = {}
    owner = meta.owning_sig
    if owner and owner in chart.label_of:
        specs[("OWNED_BY", "KEP", k, chart.label_of[owner], owner, ())] = {}
    if src.stub:
        return specs
    for org in meta.participating_sigs:
        if org in chart.label_of:
            specs[("PARTICIPATES", chart.label_of[org], org, "KEP", k, ())] = {}
    for pos, login in enumerate(meta.authors):
        specs[("AUTHORED", "Person", login, "KEP", k, ())] = {"position": pos}
    for login in meta.reviewers:
        specs[("REVIEWS", "Person", login, "KEP", k, ())] = {}
    for login in meta.approvers:
        specs[("APPROVES", "Person", login, "KEP", k, ())] = {}
    if meta.editor:
        specs[("EDITS", "Person", meta.editor, "KEP", k, ())] = {}
    for gate in meta.feature_gates:
        specs[("GATED_BY", "KEP", k, "FeatureGate", gate, ())] = {}
    for stage, release in meta.milestones.items():
        specs[("TARGETS", "KEP", k, "Release", release, (("stage", stage),))] = {}
    if meta.latest_milestone:
        specs[("LATEST", "KEP", k, "Release", meta.latest_milestone, ())] = {}
    for raw in meta.see_also_raw:
        hit = resolver.resolve(raw, k)
        if hit and hit[0] == "kep" and hit[1] != k:
            specs[("SEE_ALSO", "KEP", k, "KEP", hit[1], ())] = {"raw": raw}
        elif hit and hit[0] == "external":
            specs[("REFERS_TO", "KEP", k, "ExternalRef", hit[1], (("field", "see_also"),))] = {"raw": raw}
    for fld, raws in (("replaces", meta.replaces_raw), ("superseded_by", meta.superseded_by_raw)):
        for raw in raws:
            hit = resolver.resolve(raw, k)
            if hit and hit[0] == "external":
                specs[("REFERS_TO", "KEP", k, "ExternalRef", hit[1], (("field", fld),))] = {"raw": raw}
    return specs


def _decl_specs(src: KepSource, meta: KepMeta, resolver: RefResolver) -> dict[EdgeSpec, dict[str, Any]]:
    """Replacement declarations: ('DECL', side, successor, predecessor)."""
    specs: dict[EdgeSpec, dict[str, Any]] = {}
    for raw in meta.replaces_raw:
        hit = resolver.resolve(raw, src.key)
        if hit and hit[0] == "kep" and hit[1] != src.key:
            specs[("DECL", "successor", src.key, "KEP", hit[1], ())] = {"raw": raw}
    for raw in meta.superseded_by_raw:
        hit = resolver.resolve(raw, src.key)
        if hit and hit[0] == "kep" and hit[1] != src.key:
            specs[("DECL", "predecessor", hit[1], "KEP", src.key, ())] = {"raw": raw}
    return specs


def _replay(steps: list[tuple[int, str, dict[EdgeSpec, dict[str, Any]]]], head_url: str) -> list[Interval]:
    """Turn per-revision target sets into validity intervals (03 §3.3 close/open, replayed).

    Author dates are not monotonic along git order (rebases), so each step's time is
    clamped to be no earlier than the previous one; intervals therefore never invert.
    """
    open_: dict[EdgeSpec, tuple[int, str, dict[str, Any]]] = {}
    out: list[Interval] = []
    t_prev = 0
    for at, url, specs in steps:
        t = max(at, t_prev)
        t_prev = t
        for spec in list(open_):
            if spec not in specs:
                start, start_url, props = open_.pop(spec)
                if t > start:
                    out.append(Interval(spec, props, start, t, start_url))
        for spec, props in specs.items():
            if spec not in open_:
                open_[spec] = (t, url, props)
            else:
                open_[spec] = (open_[spec][0], open_[spec][1], props)
    for spec, (start, _url, props) in open_.items():
        out.append(Interval(spec, props, start, VALID_TO_OPEN, head_url))
    return out


def _kep_steps(
    src: KepSource, chart: OrgChart, resolver: RefResolver, decl: bool
) -> list[tuple[int, str, dict[EdgeSpec, dict[str, Any]]]]:
    steps = []
    for pr in src.revisions:
        url = blob_url(ENHANCEMENTS_REPO, pr.rev.sha, pr.rev.path)
        specs = _decl_specs(src, pr.meta, resolver) if decl else _meta_specs(src, pr.meta, chart, resolver)
        steps.append((pr.rev.at, url, specs))
    return steps


def _prr_steps(src: KepSource) -> list[tuple[int, str, dict[EdgeSpec, dict[str, Any]]]]:
    steps = []
    for pr in src.prr_revisions:
        specs: dict[EdgeSpec, dict[str, Any]] = {
            ("PRR_APPROVED", "Person", login, "KEP", src.key, (("stage", stage),)): {}
            for stage, login in pr.approvers.items()
        }
        steps.append((pr.rev.at, blob_url(ENHANCEMENTS_REPO, pr.rev.sha, pr.rev.path), specs))
    return steps


def _combine_replacements(decls: list[Interval]) -> list[Interval]:
    """Sweep successor/predecessor declarations per pair into REPLACES + SUPERSEDED_BY intervals (03 §5.3)."""
    by_pair: dict[tuple[str, str], list[Interval]] = defaultdict(list)
    for iv in decls:
        by_pair[(iv.spec[2], iv.spec[4])].append(iv)
    out: list[Interval] = []
    for (succ, pred), ivs in by_pair.items():
        points = sorted({p for iv in ivs for p in (iv.valid_from, iv.valid_to)})
        segments: list[tuple[int, int, str, Interval | None, Interval | None]] = []
        for a, b in zip(points, points[1:], strict=False):
            s = next((iv for iv in ivs if iv.spec[1] == "successor" and iv.valid_from <= a < iv.valid_to), None)
            p = next((iv for iv in ivs if iv.spec[1] == "predecessor" and iv.valid_from <= a < iv.valid_to), None)
            if not s and not p:
                continue
            state = "both" if s and p else ("successor" if s else "predecessor")
            if segments and segments[-1][1] == a and segments[-1][2] == state:
                last = segments[-1]
                segments[-1] = (last[0], b, state, last[3], last[4])
            else:
                segments.append((a, b, state, s, p))
        for a, b, state, s, p in segments:
            first = s or p
            assert first is not None
            url = first.source_url if b != VALID_TO_OPEN else (s.source_url if s else first.source_url)
            raw = (s.props.get("raw") if s else None) or (p.props.get("raw") if p else None)
            out.append(
                Interval(
                    ("REPLACES", "KEP", succ, "KEP", pred, ()),
                    {"declared_by": state, "raw": raw},
                    a,
                    b,
                    url,
                )
            )
            out.append(
                Interval(
                    ("SUPERSEDED_BY", "KEP", pred, "KEP", succ, ()),
                    {"derived": state == "successor", "raw": p.props.get("raw") if p else None},
                    a,
                    b,
                    p.source_url if p else url,
                )
            )
    return out


# --------------------------------------------------------------------------- writing


def _ref_kind(url: str) -> str:
    low = url.lower()
    if "docs.google.com" in low:
        return "google_doc"
    if "design-proposals-archive" in low:
        return "design_proposal_archive"
    if "kubernetes/community/pull" in low:
        return "community_pr"
    return "other"


def _kep_row(src: KepSource, corpus: Corpus) -> dict[str, Any]:
    m = src.head
    sha = corpus.sha
    blob = corpus.tree.get(src.yaml_path, ("", ""))[1]
    updated = corpus.dir_updated.get(src.key)
    reasons = list(m.invalid_reasons)
    for raw in m.see_also_raw + m.replaces_raw + m.superseded_by_raw:
        text = raw.strip().strip("'\"").lstrip("/")
        unresolved = text.startswith("keps/") and corpus.resolver.resolve(raw, src.key) is None
        if unresolved and "unresolved_reference" not in reasons:
            reasons.append("unresolved_reference")
    row: dict[str, Any] = {
        "key": src.key,
        "path": src.key,
        "dir_prefix": src.dir_name.split("-", 1)[0],
        "number": m.number,
        "title": m.title or src.dir_name,
        "owning_sig": m.owning_sig or src.sig_dir,
        "sig_dir": src.sig_dir,
        "status": m.status or "unknown",
        "status_raw": m.status_raw,
        "stage": m.stage,
        "stage_raw": m.stage_raw,
        "latest_milestone": m.latest_milestone,
        "metadata_invalid": bool(reasons),
        "metadata_invalid_reasons": reasons or None,
        "stub": src.stub,
        "url": tree_url(ENHANCEMENTS_REPO, sha, src.key),
        "upstream_updated_at": updated[1] if updated else corpus.sha_time,
        "source_url": tree_url(ENHANCEMENTS_REPO, sha, src.key),
        "source_repo": ENHANCEMENTS_REPO,
        "source_path": src.yaml_path,
        "source_sha": blob,
    }
    if not src.stub:
        row.update(
            {
                "latest_milestone_raw": m.latest_milestone_raw,
                "creation_date": m.creation_date,
                "creation_date_raw": m.creation_date_raw,
                "last_updated": m.last_updated,
                "last_updated_raw": m.last_updated_raw,
                "editor": m.editor,
                "disable_supported": m.disable_supported,
                "participating_raw": m.participating_raw or None,
                "see_also_raw": m.see_also_raw or None,
                "replaces_raw": m.replaces_raw or None,
                "superseded_by_raw": m.superseded_by_raw or None,
                "summary": summary_text(src.sections),
            }
        )
        for stage in MILESTONE_STAGES:
            row[f"milestone_{stage}"] = m.milestones.get(stage)
    return row


def _write_intervals(writer: BatchWriter, intervals: list[Interval], bots: set[str]) -> dict[str, int]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    idents: dict[tuple[str, str, str], list[str]] = {}
    for iv in intervals:
        rel, fl, f, tl, t, ident = iv.spec
        props = {k: v for k, v in iv.props.items() if v is not None}
        props.update(dict(ident))
        props.update(state_props(iv.valid_from, iv.valid_to, iv.source_url))
        props["w"] = path_weight(fl, tl, bot=(fl == "Person" and f in bots))
        groups[(rel, fl, tl)].append({"from": f, "to": t, "props": props})
        idents[(rel, fl, tl)] = [name for name, _ in ident] + ["valid_from"]
    counts: dict[str, int] = defaultdict(int)
    for (rel, fl, tl), rows in groups.items():
        writer.upsert_edges(rel, fl, tl, rows, identity=idents[(rel, fl, tl)])
        counts[rel] += len(rows)
    return dict(counts)


def sync_docs(writer: BatchWriter, corpus: Corpus, settings: Settings) -> dict[str, int]:
    started = time.monotonic()
    sha = corpus.sha
    chart = sync_sigs(writer, corpus.community_git, corpus.community_sha, set(corpus.in_scope_sigs))
    keps = corpus.keps
    loaded = [k for k in keps.values() if not k.stub]

    # KEP nodes (loaded + stubs)
    writer.upsert_nodes("KEP", [_kep_row(src, corpus) for src in keps.values()])

    # People: everyone named in any revision of a loaded kep.yaml or PRR file
    people: dict[str, tuple[str, str]] = {}
    for src in loaded:
        head_url = blob_url(ENHANCEMENTS_REPO, sha, src.yaml_path)
        for raw in src.head.authors_raw:
            login = normalise_login(raw)
            if login:
                people.setdefault(login, (raw.strip().lstrip("@"), head_url))
        for login in src.head.reviewers + src.head.approvers + ([src.head.editor] if src.head.editor else []):
            people.setdefault(login, (login, head_url))
    for src in loaded:
        for pr in src.revisions:
            url = blob_url(ENHANCEMENTS_REPO, pr.rev.sha, pr.rev.path)
            for login in pr.meta.authors + pr.meta.reviewers + pr.meta.approvers:
                people.setdefault(login, (login, url))
            if pr.meta.editor:
                people.setdefault(pr.meta.editor, (pr.meta.editor, url))
        for prr in src.prr_revisions:
            url = blob_url(ENHANCEMENTS_REPO, prr.rev.sha, prr.rev.path)
            for login in prr.approvers.values():
                people.setdefault(login, (login, url))
    for login in list(people):
        if login in chart.people:
            people.pop(login)  # already written by sync_sigs with its own source
    writer.upsert_nodes(
        "Person",
        [
            {
                "key": login,
                "login": login,
                "login_raw": raw,
                "url": person_url(login),
                "is_bot": is_bot(login),
                "source_url": url,
            }
            for login, (raw, url) in people.items()
        ],
    )
    bots = {login for login in list(people) + list(chart.people) if is_bot(login)}

    # Feature gates
    gates: dict[str, dict[str, Any]] = {}
    for src in loaded:
        for pr in src.revisions:
            for g in pr.meta.feature_gates:
                gates.setdefault(g, {"url": blob_url(ENHANCEMENTS_REPO, pr.rev.sha, pr.rev.path), "comps": set()})
        for g in src.head.feature_gates:
            gates.setdefault(g, {"url": "", "comps": set()})
            gates[g]["url"] = blob_url(ENHANCEMENTS_REPO, sha, src.yaml_path)
            gates[g]["comps"].update(src.head.gate_components.get(g, []))
    gate_counts: dict[str, int] = defaultdict(int)
    for src in loaded:
        for g in src.head.feature_gates:
            gate_counts[g] += 1
    writer.upsert_nodes(
        "FeatureGate",
        [
            {
                "key": g,
                "name": g,
                "components": sorted(v["comps"]) or None,
                "kep_count": gate_counts.get(g, 0),
                "source_url": v["url"],
            }
            for g, v in gates.items()
        ],
    )

    # Releases: every minor from the oldest to the newest referenced one
    minors: set[int] = set()
    for src in loaded:
        for pr in src.revisions:
            minors.update(release_minor(r) for r in pr.meta.milestones.values())
            if pr.meta.latest_milestone:
                minors.add(release_minor(pr.meta.latest_milestone))
    dates = fetch_release_dates(settings, corpus.sha_time)
    latest_ga = max((release_minor(r) for r in dates), default=0)
    release_rows = []
    for minor in range(min(minors, default=0), max(minors | {latest_ga}) + 1):
        name = f"v1.{minor}"
        released = dates.get(name)
        release_rows.append(
            {
                "key": name,
                "name": name,
                "major": 1,
                "minor": minor,
                "ordinal": minor,
                "is_future": minor > latest_ga,
                "released_at": released,
                "released_at_iso": iso(released) if released else None,
                "url": f"https://github.com/kubernetes/kubernetes/releases/tag/{name}.0"
                if released
                else f"https://github.com/{ENHANCEMENTS_REPO}/milestones?state=all&q={name}",
                "source_url": f"https://github.com/kubernetes/kubernetes/releases/tag/{name}.0"
                if released
                else f"https://github.com/{ENHANCEMENTS_REPO}/milestones?state=all&q={name}",
            }
        )
    writer.upsert_nodes("Release", release_rows)
    writer.query(
        "MATCH (a:Release), (b:Release) WHERE b.ordinal = a.ordinal + 1 MERGE (a)-[e:PRECEDES]->(b) "
        "SET e.observed_at = $t, e.sync_run_id = $run",
        {"t": writer.observed_at, "run": writer.sync_run_id},
    )

    # External references
    ext: dict[str, str] = {}
    for src in loaded:
        for pr in src.revisions:
            for raw in pr.meta.see_also_raw + pr.meta.replaces_raw + pr.meta.superseded_by_raw:
                hit = corpus.resolver.resolve(raw, src.key)
                if hit and hit[0] == "external":
                    ext.setdefault(hit[1], blob_url(ENHANCEMENTS_REPO, pr.rev.sha, pr.rev.path))
    writer.upsert_nodes(
        "ExternalRef",
        [
            {"key": u, "url": u, "host": urlsplit(u).netloc.lower(), "ref_kind": _ref_kind(u), "source_url": src_url}
            for u, src_url in ext.items()
        ],
    )

    # Documents and sections
    doc_rows: list[dict[str, Any]] = []
    has_doc: list[tuple[str, str, str]] = []
    section_rows: list[dict[str, Any]] = []
    has_section: list[dict[str, Any]] = []
    next_rows: list[dict[str, Any]] = []
    for src in loaded:
        files = [("kep_yaml", "metadata", src.yaml_path), ("kep_readme", "readme", src.readme_path)]
        if src.prr_path:
            files.append(("prr", "prr", src.prr_path))
        for kind, role, path in files:
            if path not in corpus.tree:
                continue
            last = corpus.dir_updated.get(path)
            url = blob_url(ENHANCEMENTS_REPO, sha, path)
            doc_key = f"{ENHANCEMENTS_REPO}:{path}"
            doc_rows.append(
                {
                    "key": doc_key,
                    "kind": kind,
                    "repo": ENHANCEMENTS_REPO,
                    "path": path,
                    "title": src.head.title if kind != "prr" else path.rsplit("/", 1)[-1],
                    "blob_sha": corpus.tree[path][1],
                    "last_commit_sha": last[0] if last else None,
                    "last_commit_at": last[1] if last else None,
                    "byte_size": len(src.readme_text.encode("utf-8"))
                    if kind == "kep_readme" and src.readme_text
                    else None,
                    "section_count": len(src.sections) if kind == "kep_readme" else None,
                    "url": url,
                    "source_url": url,
                    "source_repo": ENHANCEMENTS_REPO,
                    "source_path": path,
                    "source_sha": corpus.tree[path][1],
                }
            )
            has_doc.append((src.key, doc_key, role))
            if kind == "kep_readme":
                prev: str | None = None
                for s in src.sections:
                    s_key = f"{src.key}#{s.anchor}"
                    s_url = f"{url}#{s.anchor}"
                    section_rows.append(
                        {
                            "key": s_key,
                            "kep_path": src.key,
                            "anchor": s.anchor,
                            "heading": s.heading,
                            "level": s.level,
                            "order": s.order,
                            "text": s.text,
                            "char_count": s.char_count,
                            "kind": s.kind,
                            "dated_bullets": len(re.findall(r"(?m)^\s*[-*]\s*\d{4}-\d{2}-\d{2}", s.text))
                            if s.kind == "implementation_history"
                            else None,
                            "url": s_url,
                            "source_url": s_url,
                            "source_repo": ENHANCEMENTS_REPO,
                            "source_path": path,
                            "source_sha": corpus.tree[path][1],
                        }
                    )
                    has_section.append({"from": doc_key, "to": s_key, "props": {"order": s.order, "w": 1}})
                    if prev:
                        next_rows.append({"from": prev, "to": s_key, "props": {"w": 1}})
                    prev = s_key
    writer.upsert_nodes("Document", doc_rows)
    writer.upsert_nodes("Section", section_rows)
    writer.upsert_edges(
        "HAS_DOCUMENT", "KEP", "Document", [{"from": k, "to": d, "props": {"role": r, "w": 1}} for k, d, r in has_doc]
    )
    writer.upsert_edges("HAS_SECTION", "Document", "Section", has_section)
    writer.upsert_edges("NEXT", "Section", "Section", next_rows)

    # Metadata state edges, replayed over history
    intervals: list[Interval] = []
    decls: list[Interval] = []
    for src in keps.values():
        head_url = blob_url(ENHANCEMENTS_REPO, sha, src.yaml_path)
        intervals.extend(_replay(_kep_steps(src, chart, corpus.resolver, decl=False), head_url))
        decls.extend(_replay(_kep_steps(src, chart, corpus.resolver, decl=True), head_url))
        if src.prr_path and src.prr_revisions:
            intervals.extend(_replay(_prr_steps(src), blob_url(ENHANCEMENTS_REPO, sha, src.prr_path)))
    intervals.extend(_combine_replacements(decls))
    edge_counts = _write_intervals(writer, intervals, bots)
    # The replay is complete and deterministic, so any git-history interval not re-merged by this
    # run is an artefact of an earlier replay (e.g. a corrected rename rule) and is removed.
    for rel in sorted({iv.spec[0] for iv in intervals} | REPLAYED_RELS):
        writer.query(
            f"MATCH ()-[e:{rel}]->() WHERE e.valid_from_basis = 'git_history' AND e.sync_run_id <> $run DELETE e",
            {"run": writer.sync_run_id},
        )
    log.info("docs_loaded", seconds=round(time.monotonic() - started, 1), **edge_counts)
    return edge_counts
