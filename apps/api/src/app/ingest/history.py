"""Metadata history: `Commit` + `StatusChange {kind: metadata}` from `kep.yaml` revisions (03 §4.4, §7.2).

For each loaded KEP the revisions of its `kep.yaml` (oldest first, renames
followed) are diffed field by field on the *normalised* values. Each changed
field in a commit becomes one `StatusChange` chained per (`kep_path`, `field`)
with `seq`, `valid_from`/`valid_to`, `PREVIOUS` and `is_reversal`.

Commits are mapped to the pull request that merged them by walking the
first-parent history of the pinned head: every commit first reachable from a
mainline `Merge pull request #N` commit belongs to PR N; squash merges carry
`(#N)` in their own subject. Commit e-mails are never read (03 §9).
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Any

import structlog

from app.db.batch import BatchWriter
from app.ingest.common import ENHANCEMENTS_REPO, Git, Revision, blob_url, commit_url, iso, pr_url
from app.ingest.docs import Corpus
from app.ingest.kep_yaml import normalise_milestone
from app.schema.labels import VALID_TO_OPEN

log = structlog.get_logger(__name__)
MERGE_RE = re.compile(r"^Merge pull request #(\d+)\b")
SQUASH_RE = re.compile(r"\(#(\d+)\)\s*$")
RELEASE_FIELDS = frozenset(
    {"latest_milestone", *(f"milestone.{s}" for s in ("alpha", "beta", "stable", "deprecated", "disabled", "removed"))}
)


def parse_pr_number(subject: str) -> int | None:
    m = MERGE_RE.match(subject) or SQUASH_RE.search(subject)
    return int(m.group(1)) if m else None


def map_commits_to_prs(git: Git, head: str) -> dict[str, tuple[int, str]]:
    """commit sha -> (PR number, mainline commit sha) for every commit reachable from `head`."""
    parents: dict[str, list[str]] = {}
    for line in git.run("rev-list", "--parents", head).splitlines():
        parts = line.split()
        parents[parts[0]] = parts[1:]
    mainline: list[tuple[str, str]] = []
    for line in git.run("log", "--first-parent", "--format=%H%x09%s", head).splitlines():
        sha, _, subject = line.partition("\t")
        mainline.append((sha, subject))
    mainline.reverse()
    result: dict[str, tuple[int, str]] = {}
    visited: set[str] = set()
    for sha, subject in mainline:
        number = parse_pr_number(subject)
        stack = [sha]
        while stack:
            c = stack.pop()
            if c in visited:
                continue
            visited.add(c)
            if number is not None:
                result[c] = (number, sha)
            stack.extend(p for p in parents.get(c, []) if p not in visited)
    return result


def _changes_for_kep(
    kep_key: str, revisions: list[tuple[Revision, dict[str, str | None], dict[str, str | None]]]
) -> list[dict[str, Any]]:  # noqa: E501
    """Field-level diff over normalised values; returns StatusChange rows (without chain links)."""
    rows: list[dict[str, Any]] = []
    prev_vals: dict[str, str | None] = {}
    prev_raw: dict[str, str | None] = {}
    t_prev = 0
    for rev, values, raws in revisions:
        t = max(rev.at, t_prev)  # clamp: author dates are not monotonic along git order
        t_prev = t
        for fld, value in values.items():
            before = prev_vals.get(fld)
            if value == before:
                continue
            rows.append(
                {
                    "key": f"sc:{kep_key}:{fld}:{rev.sha}",
                    "kind": "metadata",
                    "kep_path": kep_key,
                    "field": fld,
                    "op": "set",
                    "from_value": before,
                    "to_value": value,
                    "from_raw": prev_raw.get(fld),
                    "to_raw": raws.get(fld),
                    "at": rev.at,
                    "at_iso": iso(rev.at),
                    "valid_from": t,
                    "commit_sha": rev.sha,
                    "source_url": blob_url(ENHANCEMENTS_REPO, rev.sha, rev.path),
                }
            )
        prev_vals = values
        prev_raw = raws
    return rows


def _chain(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Fill seq / valid_to / is_reversal per field; return PREVIOUS pairs (later -> earlier)."""
    by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_field[r["field"]].append(r)
    previous: list[tuple[str, str]] = []
    for chain in by_field.values():
        for i, r in enumerate(chain):
            r["seq"] = i + 1
            nxt = chain[i + 1] if i + 1 < len(chain) else None
            r["valid_to"] = nxt["valid_from"] if nxt else VALID_TO_OPEN
            r["valid_to_iso"] = iso(r["valid_to"])
            r["valid_from_iso"] = iso(r["valid_from"])
            prev = chain[i - 1] if i > 0 else None
            r["is_reversal"] = bool(prev and prev["from_value"] is not None and r["to_value"] == prev["from_value"])
            if prev:
                previous.append((r["key"], prev["key"]))
    return previous


def _prune_status_changes(writer: BatchWriter, keep: set[str]) -> None:
    """Delete metadata StatusChanges a previous replay produced that this replay no longer does."""
    rows = writer.query("MATCH (s:StatusChange {kind: 'metadata'}) RETURN s.key")
    stale = [r[0] for r in rows if r[0] not in keep]
    for i in range(0, len(stale), 500):
        writer.query("UNWIND $keys AS k MATCH (s:StatusChange {key: k}) DETACH DELETE s", {"keys": stale[i : i + 500]})
    if stale:
        log.info("status_changes_pruned", count=len(stale))


def sync_history(writer: BatchWriter, corpus: Corpus) -> dict[str, int]:
    started = time.monotonic()
    pr_map = map_commits_to_prs(corpus.git, corpus.sha)
    sc_rows: list[dict[str, Any]] = []
    previous: list[tuple[str, str]] = []
    commits: dict[str, dict[str, Any]] = {}
    for src in corpus.keps.values():
        if src.stub:
            continue
        revs = [(pr.rev, pr.meta.field_values(), pr.meta.raw_values()) for pr in src.revisions]
        rows = _changes_for_kep(src.key, revs)
        previous.extend(_chain(rows))
        sc_rows.extend(rows)
        for rev in [pr.rev for pr in src.revisions] + [p.rev for p in src.prr_revisions]:
            c = commits.get(rev.sha)
            if c is None:
                pr = pr_map.get(rev.sha)
                number = parse_pr_number(rev.subject) or (pr[0] if pr else None)
                c = {
                    "key": f"{ENHANCEMENTS_REPO}@{rev.sha}",
                    "sha": rev.sha,
                    "repo": ENHANCEMENTS_REPO,
                    "authored_at": rev.at,
                    "authored_at_iso": iso(rev.at),
                    "subject": rev.subject,
                    "url": commit_url(ENHANCEMENTS_REPO, rev.sha),
                    "source_url": commit_url(ENHANCEMENTS_REPO, rev.sha),
                    "source_repo": ENHANCEMENTS_REPO,
                    "pr_number": number,
                    "merge_commit_sha": pr[1] if pr and pr[1] != rev.sha else None,
                    "files_changed": [],
                }
                commits[rev.sha] = c
            if rev.path not in c["files_changed"]:
                c["files_changed"].append(rev.path)

    writer.upsert_nodes("Commit", list(commits.values()))
    writer.upsert_nodes("StatusChange", sc_rows)
    _prune_status_changes(writer, {r["key"] for r in sc_rows})

    pr_numbers = sorted({c["pr_number"] for c in commits.values() if c["pr_number"] is not None})
    pr_rows = [
        {
            "key": f"{ENHANCEMENTS_REPO}#{n}",
            "repo": ENHANCEMENTS_REPO,
            "number": n,
            "url": pr_url(ENHANCEMENTS_REPO, n),
            "source_url": pr_url(ENHANCEMENTS_REPO, n),
            "observed_at": writer.observed_at,
            "sync_run_id": writer.sync_run_id,
        }
        for n in pr_numbers
    ]
    # Minimal stubs only: lane B's ticket sync owns every other PullRequest property.
    for i in range(0, len(pr_rows), 500):
        writer.query(
            "UNWIND $rows AS r MERGE (p:PullRequest {key: r.key}) "
            "ON CREATE SET p += r, p.first_seen_at = r.observed_at, p.content_hash = '', p.stub = true "
            "SET p:Ticket",
            {"rows": pr_rows[i : i + 500]},
        )

    writer.upsert_edges(
        "CHANGED", "KEP", "StatusChange", [{"from": r["kep_path"], "to": r["key"], "props": {"w": 1}} for r in sc_rows]
    )
    writer.upsert_edges(
        "IN_COMMIT",
        "StatusChange",
        "Commit",
        [{"from": r["key"], "to": f"{ENHANCEMENTS_REPO}@{r['commit_sha']}", "props": {"w": 1}} for r in sc_rows],
    )
    writer.upsert_edges(
        "PREVIOUS", "StatusChange", "StatusChange", [{"from": a, "to": b, "props": {"w": 1}} for a, b in previous]
    )
    to_release = [
        {"from": r["key"], "to": r["to_value"], "props": {"w": 50}}
        for r in sc_rows
        if r["field"] in RELEASE_FIELDS and r["to_value"] and normalise_milestone(r["to_value"])
    ]
    writer.upsert_edges("TO_RELEASE", "StatusChange", "Release", to_release)
    writer.upsert_edges(
        "IN_PR",
        "Commit",
        "PullRequest",
        [
            {"from": c["key"], "to": f"{ENHANCEMENTS_REPO}#{c['pr_number']}", "props": {"w": 1}}
            for c in commits.values()
            if c["pr_number"] is not None
        ],
    )
    counts = {
        "commits": len(commits),
        "status_changes": len(sc_rows),
        "pull_request_stubs": len(pr_rows),
        "seconds": int(time.monotonic() - started),
    }
    log.info("history_loaded", **counts)
    return counts
