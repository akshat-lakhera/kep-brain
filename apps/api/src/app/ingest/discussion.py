"""Substantive review discussion on the enhancement PRs behind status changes (03 §4.5, §5.5).

The ticket layer keeps only Prow commands and review states. This module adds the discussion that
explains a decision: review bodies (already fetched with the PR) and inline review-thread comments
(one extra GraphQL query per `THREAD_BATCH` PRs, recorded in the GitHub cache like every other query).

A comment is substantive when its author is a person (not a bot), and its text without Prow command
lines (`/lgtm`, `/approve`, ...) is longer than `MIN_CHARS` characters. Each one becomes
`Comment {key, kind: "review_comment", source: review_body|review_thread, author_login, created_at,
excerpt (first EXCERPT_CHARS characters, e-mail addresses removed), path?, pr_number, url}` with
`(Person)-[:COMMENTED]->(Comment)-[:ON]->(PullRequest)`. Writes are MERGE on `key`, so re-runs are
idempotent. Comment bodies beyond the excerpt are not stored.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.db.batch import BatchWriter
from app.ingest.common import ENHANCEMENTS_REPO, is_bot, iso
from app.ingest.github import MAX_IN_FLIGHT, GitHubClient
from app.ingest.tickets import _COMMAND_RE, ensure_nodes, epoch, issue_key, person_row, scrub

log = structlog.get_logger(__name__)

REPO = ENHANCEMENTS_REPO
OWNER, NAME = REPO.split("/")
MIN_CHARS = 200
EXCERPT_CHARS = 600
THREAD_BATCH = 10
THREADS_PAGE = 100
COMMENTS_PER_THREAD = 20
# GraphQL points this layer may spend on uncached queries in one run (a 10-PR batch costs about 10).
BUDGET_POINTS = 1400

_THREAD_FIELDS = f"""
  number
  reviewThreads(first: {THREADS_PAGE}{{after}}) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{
      path
      comments(first: {COMMENTS_PER_THREAD}) {{
        nodes {{ databaseId createdAt url body author {{ login }} }}
      }}
    }}
  }}
"""

_THREAD_PAGE_QUERY = (
    """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  rateLimit { cost remaining }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {"""
    + _THREAD_FIELDS.replace("{after}", ", after: $after")
    + """    }
  }
}
"""
)


@dataclass
class DiscussionStats:
    prs: int = 0
    review_bodies: int = 0
    thread_comments: int = 0
    comments_seen: int = 0
    points_spent: int = 0
    prs_without_threads_fetched: int = 0
    fetched_prs: list[int] = field(default_factory=list)
    by_source: dict[str, int] = field(default_factory=dict)


def _login(author: dict[str, Any] | None) -> str | None:
    raw = (author or {}).get("login")
    return str(raw).lower() if raw else None


def _normalise(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n")


def strip_commands(body: str) -> str:
    return _COMMAND_RE.sub("", _normalise(body)).strip()


def is_substantive(body: str | None, login: str | None) -> bool:
    """A human comment whose text without Prow command lines is longer than MIN_CHARS."""
    if not body or not login or is_bot(login):
        return False
    return len(strip_commands(body)) > MIN_CHARS


def excerpt(body: str) -> str:
    return (scrub(_normalise(body).strip()[:EXCERPT_CHARS]) or "").rstrip()


def _thread_batch_query(numbers: Sequence[int]) -> str:
    fields = _THREAD_FIELDS.replace("{after}", "")
    aliases = "\n".join(f"p{n}: pullRequest(number: {n}) {{ {fields} }}" for n in numbers)
    return f'query {{ rateLimit {{ cost remaining }} repository(owner: "{OWNER}", name: "{NAME}") {{ {aliases} }} }}'


def fetch_review_threads(
    client: GitHubClient, numbers: Sequence[int], stats: DiscussionStats, budget: int = BUDGET_POINTS
) -> dict[int, list[dict[str, Any]]]:
    """PR number -> review threads ({path, comments: {nodes}}). Stops before an uncached query would
    exceed `budget` points; PRs left out are counted in `stats.prs_without_threads_fetched`."""
    out: dict[int, list[dict[str, Any]]] = {}
    ordered = sorted(set(numbers))
    chunks = [ordered[i : i + THREAD_BATCH] for i in range(0, len(ordered), THREAD_BATCH)]
    done = 0
    while done < len(chunks):
        # A wave runs up to MAX_IN_FLIGHT batches at once; its worst-case cost must fit the remaining budget.
        wave: list[list[int]] = []
        worst = stats.points_spent
        for chunk in chunks[done : done + MAX_IN_FLIGHT]:
            if worst + len(chunk) + 1 > budget:
                break
            worst += len(chunk) + 1
            wave.append(chunk)
        if not wave:
            left = sum(len(c) for c in chunks[done:])
            stats.prs_without_threads_fetched += left
            log.warning("discussion_budget_reached", spent=stats.points_spent, left_out=left)
            break
        done += len(wave)
        results = _counted_many(client, stats, [(_thread_batch_query(c), {}) for c in wave])
        for chunk, data in zip(wave, results, strict=True):
            repo = data.get("repository") or {}
            for n in chunk:
                node = repo.get(f"p{n}")
                if not node:
                    continue
                conn = node.get("reviewThreads") or {}
                threads = [t for t in conn.get("nodes") or [] if t]
                page = conn.get("pageInfo") or {}
                while page.get("hasNextPage") and stats.points_spent + 2 <= budget:
                    more_data = _counted(
                        client,
                        stats,
                        _THREAD_PAGE_QUERY,
                        {"owner": OWNER, "name": NAME, "number": n, "after": page.get("endCursor")},
                    )
                    more = ((more_data.get("repository") or {}).get("pullRequest") or {}).get("reviewThreads") or {}
                    threads.extend(t for t in more.get("nodes") or [] if t)
                    page = more.get("pageInfo") or {}
                if not page.get("hasNextPage"):
                    out[n] = threads
                    stats.fetched_prs.append(n)
                else:
                    out[n] = threads  # budget ran out mid-PR: keep what was read, but do not mark it complete
    return out


def _counted_many(
    client: GitHubClient, stats: DiscussionStats, calls: Sequence[tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    before = client.points_spent
    results = client.graphql_many(calls)
    stats.points_spent += client.points_spent - before
    return results


def _counted(client: GitHubClient, stats: DiscussionStats, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    hits = client.cache_hits
    data = client.graphql(query, variables)
    if client.cache_hits == hits:
        stats.points_spent += int((data.get("rateLimit") or {}).get("cost") or 1)
    return data


def build_rows(
    prs: dict[int, dict[str, Any]],
    threads: dict[int, list[dict[str, Any]]],
    stats: DiscussionStats,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(comment rows, COMMENTED edges, ON edges) for the substantive review bodies and thread comments."""
    rows: list[dict[str, Any]] = []
    commented: list[dict[str, Any]] = []
    on: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(raw: dict[str, Any], key: str, source: str, number: int, at_field: str, path: str | None) -> None:
        stats.comments_seen += 1
        login = _login(raw.get("author"))
        body = raw.get("body")
        if key in seen or not is_substantive(body, login):
            return
        seen.add(key)
        assert login is not None and body is not None
        at = epoch(raw.get(at_field))
        url = str(raw.get("url") or f"https://github.com/{REPO}/pull/{number}")
        rows.append(
            {
                "key": key,
                "repo": REPO,
                "id": int(raw["databaseId"]),
                "kind": "review_comment",
                "source": source,
                "author_login": login,
                "created_at": at,
                "created_at_iso": iso(at) if at else None,
                "excerpt": excerpt(body),
                "chars": len(strip_commands(body)),
                "path": path,
                "pr_number": number,
                "url": url,
                "source_url": url,
                "source_repo": REPO,
            }
        )
        stats.by_source[source] = stats.by_source.get(source, 0) + 1
        on.append({"from": key, "to": issue_key(number), "props": {"w": 1}})
        commented.append(
            {"from": login, "to": key, "props": {"at": at or 0, "at_iso": iso(at or 0), "source_url": url, "w": 1}}
        )

    for number, pr in sorted(prs.items()):
        for rv in (pr.get("reviews") or {}).get("nodes") or []:
            if rv and rv.get("databaseId") is not None:
                add(rv, f"{REPO}/pulls/reviews/{rv['databaseId']}/body", "review_body", number, "submittedAt", None)
        for thread in threads.get(number, []):
            for cm in (thread.get("comments") or {}).get("nodes") or []:
                if cm and cm.get("databaseId") is not None:
                    key = f"{REPO}/pulls/comments/{cm['databaseId']}"
                    add(cm, key, "review_thread", number, "createdAt", thread.get("path"))
    stats.prs = len(prs)
    stats.review_bodies = stats.by_source.get("review_body", 0)
    stats.thread_comments = stats.by_source.get("review_thread", 0)
    return rows, commented, on


def write_discussion(
    writer: BatchWriter,
    rows: list[dict[str, Any]],
    commented: list[dict[str, Any]],
    on: list[dict[str, Any]],
) -> None:
    people = {r["author_login"]: person_row(r["author_login"]) for r in rows}
    ensure_nodes(writer, "Person", list(people.values()))
    writer.upsert_nodes("Comment", rows)
    writer.upsert_edges("COMMENTED", "Person", "Comment", commented)
    writer.upsert_edges("ON", "Comment", "PullRequest", on)


def ingest_discussion(writer: BatchWriter, client: GitHubClient, prs: dict[int, dict[str, Any]]) -> DiscussionStats:
    """Fetch the review threads of `prs` (already fetched with their reviews) and write the substantive comments."""
    stats = DiscussionStats()
    threads = fetch_review_threads(client, list(prs), stats)
    rows, commented, on = build_rows(prs, threads, stats)
    write_discussion(writer, rows, commented, on)
    log.info(
        "discussion_done",
        prs=stats.prs,
        review_bodies=stats.review_bodies,
        thread_comments=stats.thread_comments,
        comments_seen=stats.comments_seen,
        points_spent=stats.points_spent,
        prs_without_threads_fetched=stats.prs_without_threads_fetched,
    )
    return stats
