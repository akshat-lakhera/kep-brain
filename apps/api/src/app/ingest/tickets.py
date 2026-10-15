"""Ticket layer: KEP tracking issues, their label/milestone history, and the PRs behind status changes.

Writes (03 §4.5, §5.4, §5.5):
- `Issue:Ticket` per tracking issue `kubernetes/enhancements#<KEP number>`, `TRACKED_BY` (KEP -> Issue),
  `LABELED` (Issue -> Label) and `MILESTONED` (Issue -> Release) as current-state intervals,
  `OPENED` (Person -> Issue).
- `StatusChange {kind: label|milestone}` per GraphQL timeline event (key `ghe:<event id>`) with
  `HAS_EVENT`, `CHANGED` (from every KEP tracked by the issue), `ACTED`, `PREVIOUS`, `TO_RELEASE`.
- `PullRequest:Ticket` enrichment for the PRs whose commits changed `status`, `stage`, a milestone
  field or a replacement field, with `Review`, command `Comment`, `SUBMITTED`, `COMMENTED`, `ON`,
  `OPENED`, `MERGED` and `IN_PR` (Commit -> PullRequest).
- Substantive review discussion on those PRs (`Comment {kind: review_comment}` with a 600-character
  excerpt), written by `app.ingest.discussion`.

Titles are scrubbed; issue comments are kept only for the Prow commands they carry.
Timelines are fetched one issue per query because batched aliases silently truncate `timelineItems`
(recon `.recon/contradictions/gql-timeline-batch-probe.json`); issue metadata and PRs are batched 25
per query (recon `gql-batch25-vs-single.json`, `gql-pr-batch25-vs-single.json`).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from ulid import ULID

from app.db.batch import BatchWriter
from app.db.falkordb import GRAPH_KEP, FalkorPool
from app.ingest.common import ENHANCEMENTS_REPO, is_bot, iso, path_weight, person_url, pr_url
from app.ingest.github import GitHubClient
from app.schema.labels import NODE_LABELS, REL_TYPES, VALID_TO_OPEN
from app.settings import Settings

log = structlog.get_logger(__name__)

REPO = ENHANCEMENTS_REPO
OWNER, NAME = REPO.split("/")
ISSUE_BATCH = 25
PR_BATCH = 25
PAGE = 100
PR_TRIGGER_FIELDS = ("status", "stage", "latest_milestone", "replaces", "superseded_by")
COMMANDS = ("approve", "lgtm", "hold", "retest", "milestone", "label", "stage")
_COMMAND_RE = re.compile(r"^\s*/(" + "|".join(COMMANDS) + r")\b[ \t]*([^\r\n]*)$", re.MULTILINE)
_RELEASE_RE = re.compile(r"^v?1\.(\d{1,3})$")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_KEEP_REVIEW_STATES = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
STAGE_PREFIX = "stage/"


# -- pure helpers (unit-tested) ---------------------------------------------------


def epoch(ts: str | None) -> int | None:
    if not ts:
        return None
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())


def scrub(text: str | None) -> str | None:
    if text is None:
        return None
    return _EMAIL_RE.sub("[email removed]", text)


def release_key(title: str | None) -> str | None:
    """`"v1.31"`/`"1.31"` -> `"v1.31"`; anything else -> None (not a Release)."""
    if not title:
        return None
    m = _RELEASE_RE.match(title.strip())
    return f"v1.{int(m.group(1))}" if m else None


def parse_commands(body: str | None) -> list[str]:
    """Prow commands on their own line: `/approve`, `/lgtm cancel`, ... in order, de-duplicated."""
    if not body:
        return []
    found: list[str] = []
    for m in _COMMAND_RE.finditer(body.replace("\r\n", "\n").replace("\r", "\n")):
        arg = m.group(2).strip()
        cmd = f"/{m.group(1)}" + (f" {arg.split()[0].lower()}" if arg else "")
        if cmd not in found:
            found.append(cmd)
    return found


_STAGE_ORDER = {"alpha": 1, "beta": 2, "stable": 3, "deprecated": 4, "disabled": 5, "removed": 6}


def _stage_rank(label: str) -> int:
    return _STAGE_ORDER.get(label.removeprefix(STAGE_PREFIX), 0)


def label_category(name: str) -> str:
    prefix = name.split("/", 1)[0] if "/" in name else ""
    return prefix if prefix in {"sig", "wg", "stage", "tracked", "kind", "lifecycle", "priority", "area"} else "other"


def login_of(actor: dict[str, Any] | None) -> str | None:
    if not actor or not actor.get("login"):
        return None
    return str(actor["login"]).lower()


def issue_key(number: int) -> str:
    return f"{REPO}#{number}"


def issue_url(number: int) -> str:
    return f"https://github.com/{REPO}/issues/{number}"


@dataclass
class TimelineChange:
    key: str
    kind: str  # label | milestone
    field: str
    op: str
    from_value: str | None
    to_value: str | None
    at: int
    actor_login: str | None
    event_id: str
    seq: int = 0
    valid_to: int = VALID_TO_OPEN
    is_reversal: bool = False
    previous_key: str | None = None
    release: str | None = None


def build_timeline_changes(events: Sequence[dict[str, Any]]) -> list[TimelineChange]:
    """Turn GraphQL label/milestone timeline events into ordered StatusChange rows.

    `field` is the label name for label events and `milestone` for milestone events; `seq`,
    `valid_to` and `PREVIOUS` chain per field. `is_reversal` marks a move backwards: a `stage/*`
    label added whose stage is lower than the previously added stage label (KEP-1287 stage/stable ->
    stage/beta on 2025-06-09; KEP-4671 stage/beta -> stage/alpha on 2026-02-10), and a milestone
    change back to the milestone it replaced. Plain add/remove pairs of one label (lifecycle churn)
    are not reversals.
    """
    ordered = sorted(
        (e for e in events if e.get("id") and e.get("createdAt")),
        key=lambda e: epoch(e["createdAt"]) or 0,
    )
    changes: list[TimelineChange] = []
    current_milestone: str | None = None
    stage_history: list[str] = []  # stage label added, in order
    for ev in ordered:
        typename = ev.get("__typename")
        at = epoch(ev["createdAt"]) or 0
        actor = login_of(ev.get("actor"))
        if typename in ("LabeledEvent", "UnlabeledEvent"):
            name = (ev.get("label") or {}).get("name")
            if not name:
                continue
            added = typename == "LabeledEvent"
            reversal = False
            if added and name.startswith(STAGE_PREFIX):
                reversal = bool(stage_history) and _stage_rank(name) < _stage_rank(stage_history[-1])
                stage_history.append(name)
            changes.append(
                TimelineChange(
                    key=f"ghe:{ev['id']}",
                    kind="label",
                    field=name,
                    op="added" if added else "removed",
                    from_value=None if added else name,
                    to_value=name if added else None,
                    at=at,
                    actor_login=actor,
                    event_id=str(ev["id"]),
                    is_reversal=reversal,
                )
            )
        elif typename in ("MilestonedEvent", "DemilestonedEvent"):
            raw = ev.get("milestoneTitle")
            if not raw:
                continue
            value = release_key(raw) or raw
            if typename == "MilestonedEvent":
                change = TimelineChange(
                    key=f"ghe:{ev['id']}",
                    kind="milestone",
                    field="milestone",
                    op="milestoned",
                    from_value=current_milestone,
                    to_value=value,
                    at=at,
                    actor_login=actor,
                    event_id=str(ev["id"]),
                    release=release_key(raw),
                )
                current_milestone = value
            else:
                change = TimelineChange(
                    key=f"ghe:{ev['id']}",
                    kind="milestone",
                    field="milestone",
                    op="demilestoned",
                    from_value=value,
                    to_value=None,
                    at=at,
                    actor_login=actor,
                    event_id=str(ev["id"]),
                )
                if current_milestone == value:
                    current_milestone = None
            changes.append(change)
    # chain per field
    by_field: dict[str, list[TimelineChange]] = defaultdict(list)
    for ch in changes:
        by_field[ch.field].append(ch)
    for chain in by_field.values():
        for i, ch in enumerate(chain):
            ch.seq = i + 1
            if i > 0:
                prev = chain[i - 1]
                ch.previous_key = prev.key
                if ch.kind == "milestone" and ch.op == "milestoned":
                    # back to the milestone the previous non-empty move replaced
                    moves = [c for c in chain[:i] if c.op == "milestoned"]
                    if moves and moves[-1].from_value is not None and moves[-1].from_value == ch.to_value:
                        ch.is_reversal = True
            if i + 1 < len(chain):
                ch.valid_to = chain[i + 1].at
    return changes


def label_valid_from(changes: Sequence[TimelineChange], label: str) -> int | None:
    adds = [c.at for c in changes if c.kind == "label" and c.field == label and c.op == "added"]
    return max(adds) if adds else None


def milestone_valid_from(changes: Sequence[TimelineChange], release: str) -> int | None:
    moves = [c.at for c in changes if c.op == "milestoned" and c.to_value == release]
    return max(moves) if moves else None


# -- GraphQL --------------------------------------------------------------------

_ISSUE_FIELDS = """
  __typename
  ... on Issue {
    number title state stateReason createdAt closedAt updatedAt url
    author { login }
    milestone { title number url state }
    labels(first: 100) { nodes { name } }
    comments { totalCount }
  }
"""

_TIMELINE_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      timelineItems(first: 100, after: $after,
                    itemTypes: [LABELED_EVENT, UNLABELED_EVENT, MILESTONED_EVENT, DEMILESTONED_EVENT]) {
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on LabeledEvent { id createdAt actor { login } label { name } }
          ... on UnlabeledEvent { id createdAt actor { login } label { name } }
          ... on MilestonedEvent { id createdAt actor { login } milestoneTitle }
          ... on DemilestonedEvent { id createdAt actor { login } milestoneTitle }
        }
      }
    }
  }
}
"""

_PR_FIELDS = """
  number title state createdAt mergedAt url baseRefName
  author { login }
  mergedBy { login }
  mergeCommit { oid }
  reviews(first: 100) {
    pageInfo { hasNextPage endCursor }
    nodes { databaseId state submittedAt url body author { login } commit { oid } }
  }
  comments(first: 100) {
    pageInfo { hasNextPage endCursor }
    nodes { databaseId createdAt url body author { login } }
  }
"""

_PR_PAGE_QUERIES = {
    "reviews": """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { databaseId state submittedAt url body author { login } commit { oid } }
      }
    }
  }
}
""",
    "comments": """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      comments(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { databaseId createdAt url body author { login } }
      }
    }
  }
}
""",
}


def _batched(items: Sequence[int], size: int) -> Iterable[Sequence[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_issues(client: GitHubClient, numbers: Sequence[int]) -> dict[int, dict[str, Any]]:
    """Issue metadata, 25 aliases per query. Numbers that are PRs or missing are left out."""
    out: dict[int, dict[str, Any]] = {}
    for chunk in _batched(sorted(set(numbers)), ISSUE_BATCH):
        aliases = "\n".join(f"i{n}: issueOrPullRequest(number: {n}) {{ {_ISSUE_FIELDS} }}" for n in chunk)
        query = f'query {{ repository(owner: "{OWNER}", name: "{NAME}") {{ {aliases} }} }}'
        data = client.graphql(query)
        repo = data.get("repository") or {}
        for n in chunk:
            node = repo.get(f"i{n}")
            if node and node.get("__typename") == "Issue":
                out[n] = node
            else:
                log.info("tracking_issue_not_an_issue", number=n, typename=(node or {}).get("__typename"))
    return out


def fetch_timeline(client: GitHubClient, number: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        data = client.graphql(_TIMELINE_QUERY, {"owner": OWNER, "name": NAME, "number": number, "after": after})
        conn = ((data.get("repository") or {}).get("issue") or {}).get("timelineItems") or {}
        events.extend(n for n in conn.get("nodes") or [] if n)
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return events
        after = page.get("endCursor")


def fetch_prs(client: GitHubClient, numbers: Sequence[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for chunk in _batched(sorted(set(numbers)), PR_BATCH):
        aliases = "\n".join(f"p{n}: pullRequest(number: {n}) {{ {_PR_FIELDS} }}" for n in chunk)
        query = f'query {{ repository(owner: "{OWNER}", name: "{NAME}") {{ {aliases} }} }}'
        data = client.graphql(query)
        repo = data.get("repository") or {}
        for n in chunk:
            node = repo.get(f"p{n}")
            if node:
                _complete_pr_pages(client, node)
                out[n] = node
    return out


def _complete_pr_pages(client: GitHubClient, pr: dict[str, Any]) -> None:
    for conn_name in ("reviews", "comments"):
        conn = pr.get(conn_name) or {}
        page = conn.get("pageInfo") or {}
        while page.get("hasNextPage"):
            data = client.graphql(
                _PR_PAGE_QUERIES[conn_name],
                {"owner": OWNER, "name": NAME, "number": pr["number"], "after": page.get("endCursor")},
            )
            more = (((data.get("repository") or {}).get("pullRequest") or {}).get(conn_name)) or {}
            conn.setdefault("nodes", []).extend(n for n in more.get("nodes") or [] if n)
            page = more.get("pageInfo") or {}


# -- graph writes ---------------------------------------------------------------


def _check(rel: str, *labels: str) -> None:
    if rel not in REL_TYPES or any(lab not in NODE_LABELS for lab in labels):
        raise ValueError(f"not in allow-list: {rel} {labels}")


def ensure_nodes(writer: BatchWriter, label: str, rows: Sequence[dict[str, Any]]) -> None:
    """Create entity nodes introduced by a mention without overwriting another writer's properties."""
    if label not in NODE_LABELS:
        raise ValueError(label)
    if not rows:
        return
    for i in range(0, len(rows), 500):
        writer.query(
            f"UNWIND $rows AS r MERGE (n:{label} {{key: r.key}}) "
            "ON CREATE SET n += r, n.first_seen_at = $now, n.observed_at = $now, n.sync_run_id = $run",
            {"rows": [{k: v for k, v in r.items() if v is not None} for r in rows[i : i + 500]],
             "now": writer.observed_at, "run": writer.sync_run_id},
        )  # fmt: skip


def merge_open_state_edges(
    writer: BatchWriter, rel: str, from_label: str, to_label: str, rows: Sequence[dict[str, Any]]
) -> None:
    """Open interval per (from, rel, to): created once with its envelope, then only re-observed (03 §3.3)."""
    _check(rel, from_label, to_label)
    prepared = [
        {"from": r["from"], "to": r["to"], "props": {k: v for k, v in r["props"].items() if v is not None}}
        for r in rows
    ]
    for i in range(0, len(prepared), 500):
        writer.query(
            f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.from}}) MATCH (b:{to_label} {{key: r.to}}) "
            f"MERGE (a)-[e:{rel} {{valid_to: $open}}]->(b) "
            "ON CREATE SET e += r.props, e.observed_at = $now, e.sync_run_id = $run "
            "ON MATCH SET e.observed_at = $now, e.sync_run_id = $run",
            {"rows": prepared[i : i + 500], "open": VALID_TO_OPEN, "now": writer.observed_at,
             "run": writer.sync_run_id},
        )  # fmt: skip


def close_absent_state_edges(
    writer: BatchWriter, rel: str, from_label: str, to_label: str, current: dict[str, list[str]], at: int
) -> None:
    """For each subject key, close open `rel` edges whose target is not in its current set."""
    _check(rel, from_label, to_label)
    rows = [{"key": k, "current": v} for k, v in current.items()]
    for i in range(0, len(rows), 500):
        writer.query(
            f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.key}})-[e:{rel}]->(b:{to_label}) "
            "WHERE e.valid_to = $open AND NOT b.key IN r.current SET e.valid_to = $at, e.valid_to_iso = $at_iso",
            {"rows": rows[i : i + 500], "open": VALID_TO_OPEN, "at": at, "at_iso": iso(at)},
        )


def person_row(login: str, raw: str | None = None) -> dict[str, Any]:
    return {
        "key": login,
        "login": login,
        "login_raw": raw or login,
        "url": person_url(login),
        "source_url": person_url(login),
        "is_bot": is_bot(login),
    }


def event_props(at: int, source_url: str, *labels: str, bot: bool = False) -> dict[str, Any]:
    return {"at": at, "at_iso": iso(at), "source_url": source_url, "w": path_weight(*labels, bot=bot)}


def _latest_ga_minor(writer: BatchWriter) -> int | None:
    rows = writer.query("MATCH (r:Release) WHERE r.is_future = false RETURN max(r.minor)")
    value = rows[0][0] if rows else None
    return int(value) if value is not None else None


@dataclass
class TicketStats:
    keps: int = 0
    issues: int = 0
    not_issues: int = 0
    events: int = 0
    labels: int = 0
    releases_created: int = 0
    prs: int = 0
    reviews: int = 0
    command_comments: int = 0
    github_requests: int = 0
    cache_hits: int = 0
    extra: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, int]:
        return {k: v for k, v in self.__dict__.items() if k != "extra"} | self.extra


def _tracked_keps(writer: BatchWriter) -> dict[int, list[str]]:
    rows = writer.query(
        "MATCH (k:KEP) WHERE k.number IS NOT NULL AND k.number > 0 AND coalesce(k.stub, false) = false "
        "AND coalesce(k.archived, false) = false RETURN k.number, k.key"
    )
    by_number: dict[int, list[str]] = defaultdict(list)
    for number, key in rows:
        by_number[int(number)].append(str(key))
    return {n: sorted(keys) for n, keys in by_number.items()}


def write_releases(writer: BatchWriter, milestones: dict[str, dict[str, Any]], stats: TicketStats) -> None:
    """Create `Release` nodes for milestones not loaded yet; add milestone number/url to all of them."""
    if not milestones:
        return
    existing = {
        str(r[0]) for r in writer.query("MATCH (r:Release) WHERE r.key IN $k RETURN r.key", {"k": list(milestones)})
    }
    ga = _latest_ga_minor(writer)
    rows = []
    for key, ms in milestones.items():
        minor = int(key.split(".")[1])
        is_future = (minor > ga) if ga is not None else (str(ms.get("state")) == "OPEN")
        rows.append(
            {
                "key": key,
                "name": key,
                "major": 1,
                "minor": minor,
                "ordinal": minor,
                "is_future": is_future,
                "url": ms.get("url"),
                "source_url": ms.get("url"),
                "source_repo": REPO,
            }
        )
    stats.releases_created += sum(1 for r in rows if r["key"] not in existing)
    ensure_nodes(writer, "Release", rows)
    writer.query(
        "UNWIND $rows AS r MATCH (n:Release {key: r.key}) SET n.milestone_number = r.number, n.milestone_url = r.url",
        {"rows": [{"key": k, "number": m.get("number"), "url": m.get("url")} for k, m in milestones.items()]},
    )


def write_issues(
    writer: BatchWriter,
    keps_by_number: dict[int, list[str]],
    issues: dict[int, dict[str, Any]],
    timelines: dict[int, list[TimelineChange]],
    stats: TicketStats,
) -> None:
    now = writer.observed_at
    people: dict[str, dict[str, Any]] = {}
    label_rows: dict[str, dict[str, Any]] = {}
    milestones: dict[str, dict[str, Any]] = {}
    issue_rows: list[dict[str, Any]] = []
    tracked: list[dict[str, Any]] = []
    opened: list[dict[str, Any]] = []
    labeled: list[dict[str, Any]] = []
    milestoned: list[dict[str, Any]] = []
    current_labels: dict[str, list[str]] = {}
    current_ms: dict[str, list[str]] = {}
    current_tracked: dict[str, list[str]] = {}

    for number, node in issues.items():
        key = issue_key(number)
        url = node.get("url") or issue_url(number)
        labels = [str(lab["name"]) for lab in (node.get("labels") or {}).get("nodes") or [] if lab]
        ms = node.get("milestone") or {}
        ms_title = ms.get("title")
        ms_key = release_key(ms_title)
        if ms_key:
            milestones[ms_key] = ms
        author = login_of(node.get("author"))
        created = epoch(node.get("createdAt"))
        closed = epoch(node.get("closedAt"))
        updated = epoch(node.get("updatedAt"))
        issue_rows.append(
            {
                "key": key,
                "repo": REPO,
                "number": number,
                "title": scrub(node.get("title")),
                "state": str(node.get("state", "")).lower(),
                "state_reason": str(node["stateReason"]).lower() if node.get("stateReason") else None,
                "author_login": author,
                "created_at": created,
                "created_at_iso": iso(created) if created else None,
                "updated_at": updated,
                "updated_at_iso": iso(updated) if updated else None,
                "closed_at": closed,
                "closed_at_iso": iso(closed) if closed else None,
                "comments_count": (node.get("comments") or {}).get("totalCount"),
                "labels_current": labels,
                "milestone_current": ms_key or ms_title,
                "is_tracking_issue": True,
                "url": url,
                "source_url": url,
                "source_repo": REPO,
            }
        )
        if author:
            people[author] = person_row(author, (node.get("author") or {}).get("login"))
            opened.append({"from": author, "to": key, "props": event_props(created or now, url, bot=is_bot(author))})
        changes = timelines.get(number, [])
        current_labels[key] = labels
        for lab in labels:
            label_rows[lab] = {"key": lab, "name": lab, "category": label_category(lab), "source_url": url}
            vf = label_valid_from(changes, lab)
            labeled.append(
                {
                    "from": key,
                    "to": lab,
                    "props": _state(vf or now, url, "event" if vf else "first_observed") | {"w": 50},
                }
            )
        current_ms[key] = [ms_key] if ms_key else []
        if ms_key:
            vf = milestone_valid_from(changes, ms_key)
            milestoned.append(
                {
                    "from": key,
                    "to": ms_key,
                    "props": _state(vf or now, url, "event" if vf else "first_observed") | {"w": 50},
                }
            )
        for kep_key in keps_by_number.get(number, []):
            current_tracked[kep_key] = [key]
            tracked.append(
                {"from": kep_key, "to": key, "props": _state(created or now, url, "first_observed") | {"w": 1}}
            )
        for ch in changes:
            if ch.actor_login:
                people.setdefault(ch.actor_login, person_row(ch.actor_login))
            if ch.kind == "label":
                label_rows.setdefault(
                    ch.field,
                    {"key": ch.field, "name": ch.field, "category": label_category(ch.field), "source_url": url},
                )
            if ch.release and ch.release not in milestones:
                milestones[ch.release] = {}

    # KEPs whose number has no Issue (a PR number, or missing) lose any earlier TRACKED_BY interval.
    for number, keps in keps_by_number.items():
        if number not in issues:
            for kep_key in keps:
                current_tracked.setdefault(kep_key, [])

    ensure_nodes(writer, "Person", list(people.values()))
    ensure_nodes(writer, "Label", list(label_rows.values()))
    write_releases(writer, milestones, stats)
    writer.upsert_nodes("Issue", issue_rows, extra_labels=["Ticket"])
    close_absent_state_edges(writer, "TRACKED_BY", "KEP", "Issue", current_tracked, now)
    merge_open_state_edges(writer, "TRACKED_BY", "KEP", "Issue", tracked)
    close_absent_state_edges(writer, "LABELED", "Issue", "Label", current_labels, now)
    merge_open_state_edges(writer, "LABELED", "Issue", "Label", labeled)
    close_absent_state_edges(writer, "MILESTONED", "Issue", "Release", current_ms, now)
    merge_open_state_edges(writer, "MILESTONED", "Issue", "Release", milestoned)
    writer.upsert_edges("OPENED", "Person", "Issue", opened)
    stats.issues = len(issue_rows)
    stats.labels = len(label_rows)
    write_timeline(writer, keps_by_number, timelines, stats)


def _state(valid_from: int, source_url: str, basis: str) -> dict[str, Any]:
    return {
        "valid_from": valid_from,
        "valid_from_iso": iso(valid_from),
        "valid_to_iso": iso(VALID_TO_OPEN),
        "valid_from_basis": basis,
        "source_url": source_url,
    }


def write_timeline(
    writer: BatchWriter,
    keps_by_number: dict[int, list[str]],
    timelines: dict[int, list[TimelineChange]],
    stats: TicketStats,
) -> None:
    sc_rows: list[dict[str, Any]] = []
    has_event: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    acted: list[dict[str, Any]] = []
    previous: list[dict[str, Any]] = []
    to_release: list[dict[str, Any]] = []
    for number, changes in timelines.items():
        keps = keps_by_number.get(number, [])
        if not keps:
            continue
        ikey = issue_key(number)
        url = issue_url(number)
        for ch in changes:
            sc_rows.append(
                {
                    "key": ch.key,
                    "kind": ch.kind,
                    "kep_path": keps[0],
                    "field": ch.field,
                    "op": ch.op,
                    "from_value": ch.from_value,
                    "to_value": ch.to_value,
                    "at": ch.at,
                    "at_iso": iso(ch.at),
                    "actor_login": ch.actor_login,
                    "seq": ch.seq,
                    "valid_from": ch.at,
                    "valid_to": ch.valid_to,
                    "is_reversal": ch.is_reversal,
                    "event_id": ch.event_id,
                    "issue_number": number,
                    "source_url": url,
                    "source_repo": REPO,
                }
            )
            has_event.append({"from": ikey, "to": ch.key, "props": {}})
            changed.extend({"from": k, "to": ch.key, "props": {"w": 1}} for k in keps)
            if ch.actor_login:
                acted.append(
                    {"from": ch.actor_login, "to": ch.key, "props": event_props(ch.at, url, bot=is_bot(ch.actor_login))}
                )
            if ch.previous_key:
                previous.append({"from": ch.key, "to": ch.previous_key, "props": {}})
            if ch.release:
                to_release.append({"from": ch.key, "to": ch.release, "props": {"w": 50}})
    writer.upsert_nodes("StatusChange", sc_rows)
    writer.upsert_edges("HAS_EVENT", "Issue", "StatusChange", has_event)
    writer.upsert_edges("CHANGED", "KEP", "StatusChange", changed)
    writer.upsert_edges("ACTED", "Person", "StatusChange", acted)
    writer.upsert_edges("PREVIOUS", "StatusChange", "StatusChange", previous)
    writer.upsert_edges("TO_RELEASE", "StatusChange", "Release", to_release)
    stats.events = len(sc_rows)


def _pr_targets(writer: BatchWriter) -> dict[int, list[str]]:
    """PR number -> commit keys, for commits that carry a status/stage/milestone/replacement change."""
    rows = writer.query(
        "MATCH (sc:StatusChange {kind: 'metadata'})-[:IN_COMMIT]->(c:Commit) "
        "WHERE c.pr_number IS NOT NULL AND (sc.field IN $fields OR sc.field STARTS WITH 'milestone.') "
        "RETURN DISTINCT c.pr_number, c.key",
        {"fields": list(PR_TRIGGER_FIELDS)},
    )
    out: dict[int, list[str]] = defaultdict(list)
    for number, ckey in rows:
        out[int(number)].append(str(ckey))
    return out


def write_prs(
    writer: BatchWriter, prs: dict[int, dict[str, Any]], commits: dict[int, list[str]], stats: TicketStats
) -> None:
    people: dict[str, dict[str, Any]] = {}
    pr_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    comment_rows: list[dict[str, Any]] = []
    opened: list[dict[str, Any]] = []
    merged: list[dict[str, Any]] = []
    submitted: list[dict[str, Any]] = []
    commented: list[dict[str, Any]] = []
    review_on: list[dict[str, Any]] = []
    comment_on: list[dict[str, Any]] = []
    in_pr: list[dict[str, Any]] = []

    def person(raw: dict[str, Any] | None) -> str | None:
        login = login_of(raw)
        if login:
            people.setdefault(login, person_row(login, (raw or {}).get("login")))
        return login

    for number, pr in prs.items():
        key = issue_key(number)
        url = pr.get("url") or pr_url(REPO, number)
        author = person(pr.get("author"))
        merger = person(pr.get("mergedBy"))
        created = epoch(pr.get("createdAt"))
        merged_at = epoch(pr.get("mergedAt"))
        pr_rows.append(
            {
                "key": key,
                "repo": REPO,
                "number": number,
                "title": scrub(pr.get("title")),
                "state": str(pr.get("state", "")).lower(),
                "created_at": created,
                "created_at_iso": iso(created) if created else None,
                "merged_at": merged_at,
                "merged_at_iso": iso(merged_at) if merged_at else None,
                "merged_by_login": merger,
                "merge_commit_sha": (pr.get("mergeCommit") or {}).get("oid"),
                "base_ref": pr.get("baseRefName"),
                "stub": False,
                "author_login": author,
                "url": url,
                "source_url": url,
                "source_repo": REPO,
            }
        )
        if author:
            opened.append({"from": author, "to": key, "props": event_props(created or 0, url, bot=is_bot(author))})
        if merger and merged_at:
            merged.append({"from": merger, "to": key, "props": event_props(merged_at, url, bot=is_bot(merger))})
        for ckey in commits.get(number, []):
            in_pr.append({"from": ckey, "to": key, "props": {"w": 1}})
        for rv in (pr.get("reviews") or {}).get("nodes") or []:
            if not rv or rv.get("databaseId") is None:
                continue
            cmds = parse_commands(rv.get("body"))
            state = str(rv.get("state", ""))
            if state not in _KEEP_REVIEW_STATES and not cmds:
                continue
            login = person(rv.get("author"))
            at = epoch(rv.get("submittedAt"))
            rkey = f"{REPO}/pulls/reviews/{rv['databaseId']}"
            rurl = rv.get("url") or url
            review_rows.append(
                {
                    "key": rkey,
                    "repo": REPO,
                    "id": int(rv["databaseId"]),
                    "state": state,
                    "commands": cmds,
                    "has_command": bool(cmds),
                    "author_login": login,
                    "submitted_at": at,
                    "submitted_at_iso": iso(at) if at else None,
                    "commit_sha": (rv.get("commit") or {}).get("oid"),
                    "pr_number": number,
                    "url": rurl,
                    "source_url": rurl,
                    "source_repo": REPO,
                }
            )
            review_on.append({"from": rkey, "to": key, "props": {"w": 1}})
            if login:
                submitted.append({"from": login, "to": rkey, "props": event_props(at or 0, rurl, bot=is_bot(login))})
        for cm in (pr.get("comments") or {}).get("nodes") or []:
            if not cm or cm.get("databaseId") is None:
                continue
            cmds = parse_commands(cm.get("body"))
            if not cmds:
                continue
            login = person(cm.get("author"))
            at = epoch(cm.get("createdAt"))
            ckey = f"{REPO}/issues/comments/{cm['databaseId']}"
            curl = cm.get("url") or url
            comment_rows.append(
                {
                    "key": ckey,
                    "repo": REPO,
                    "id": int(cm["databaseId"]),
                    "kind": "issue_comment",
                    "commands": cmds,
                    "has_command": True,
                    "author_login": login,
                    "created_at": at,
                    "created_at_iso": iso(at) if at else None,
                    "pr_number": number,
                    "url": curl,
                    "source_url": curl,
                    "source_repo": REPO,
                }
            )
            comment_on.append({"from": ckey, "to": key, "props": {"w": 1}})
            if login:
                commented.append({"from": login, "to": ckey, "props": event_props(at or 0, curl, bot=is_bot(login))})

    ensure_nodes(writer, "Person", list(people.values()))
    writer.upsert_nodes("PullRequest", pr_rows, extra_labels=["Ticket"])
    writer.upsert_nodes("Review", review_rows)
    writer.upsert_nodes("Comment", comment_rows)
    writer.upsert_edges("OPENED", "Person", "PullRequest", opened)
    writer.upsert_edges("MERGED", "Person", "PullRequest", merged)
    writer.upsert_edges("SUBMITTED", "Person", "Review", submitted)
    writer.upsert_edges("COMMENTED", "Person", "Comment", commented)
    writer.upsert_edges("ON", "Review", "PullRequest", review_on)
    writer.upsert_edges("ON", "Comment", "PullRequest", comment_on)
    writer.upsert_edges("IN_PR", "Commit", "PullRequest", in_pr)
    stats.prs = len(pr_rows)
    stats.reviews = len(review_rows)
    stats.command_comments = len(comment_rows)


def sync_tickets(
    pool: FalkorPool,
    settings: Settings,
    *,
    graph: str = GRAPH_KEP,
    client: GitHubClient | None = None,
) -> dict[str, int]:
    """Fetch tracking issues (+ label/milestone history) for every loaded KEP, then the status-change PRs."""
    writer = BatchWriter(pool, graph, f"tickets:{ULID()}")
    stats = TicketStats()
    keps_by_number = _tracked_keps(writer)
    stats.keps = sum(len(v) for v in keps_by_number.values())
    if not keps_by_number:
        log.warning("sync_tickets_no_keps", graph=graph)
        return stats.as_dict()
    own_client = client is None
    gh = client or GitHubClient.from_settings(settings)
    try:
        issues = fetch_issues(gh, list(keps_by_number))
        stats.not_issues = len(keps_by_number) - len(issues)
        timelines = {n: build_timeline_changes(fetch_timeline(gh, n)) for n in sorted(issues)}
        write_issues(writer, keps_by_number, issues, timelines, stats)
        targets = _pr_targets(writer)
        prs = fetch_prs(gh, list(targets))
        write_prs(writer, prs, targets, stats)
        # Imported here: the discussion layer builds on this module's helpers.
        from app.ingest.discussion import ingest_discussion

        disc = ingest_discussion(writer, gh, prs)
        stats.extra.update(
            review_comments=disc.review_bodies + disc.thread_comments,
            discussion_points=disc.points_spent,
            prs_without_threads=disc.prs_without_threads_fetched,
        )
        stats.github_requests = gh.requests_made
        stats.cache_hits = gh.cache_hits
    finally:
        if own_client:
            gh.close()
    log.info("sync_tickets_done", **stats.as_dict())
    return stats.as_dict()
