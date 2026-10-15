"""Substantive review-comment selection, excerpts and the GraphQL budget guard (no network, no graph)."""

from __future__ import annotations

import re
from typing import Any, cast

from app.ingest.discussion import (
    EXCERPT_CHARS,
    DiscussionStats,
    build_rows,
    excerpt,
    fetch_review_threads,
    is_substantive,
)
from app.ingest.github import GitHubClient

LONG = "This changes the API contract for existing clients, so we need a deprecation period first. " * 3


def test_is_substantive() -> None:
    assert is_substantive(LONG, "wojtek-t")
    assert not is_substantive(LONG, None)  # deleted account
    assert not is_substantive(LONG, "k8s-ci-robot")
    assert not is_substantive(LONG, "dependabot[bot]")
    assert not is_substantive("short but fine", "wojtek-t")
    assert not is_substantive("/lgtm\n/approve\n" + "x" * 150, "wojtek-t")  # commands do not count
    assert is_substantive("/lgtm\n" + LONG, "wojtek-t")


def test_excerpt_bounds_and_scrubs_email() -> None:
    text = excerpt("contact me at someone@example.com\r\n" + "y" * 1000)
    assert "[email removed]" in text and "@example.com" not in text
    assert len(text) <= EXCERPT_CHARS + len("[email removed]")


def _review(i: int, body: str, login: str = "dom4ha") -> dict[str, Any]:
    return {"databaseId": i, "state": "COMMENTED", "submittedAt": "2025-09-23T10:07:49Z",
            "url": f"https://github.com/kubernetes/enhancements/pull/1#pullrequestreview-{i}", "body": body,
            "author": {"login": login}}  # fmt: skip


def test_build_rows() -> None:
    prs = {
        1: {
            "reviews": {"nodes": [_review(10, LONG, "Dom4ha"), _review(11, "/lgtm"), _review(12, LONG, "k8s-ci-robot")]}
        }
    }
    thread_comment = {"databaseId": 20, "createdAt": "2025-09-24T00:00:00Z", "body": LONG,
                      "author": {"login": "macsko"},
                      "url": "https://github.com/kubernetes/enhancements/pull/1#discussion_r20"}  # fmt: skip
    threads = {1: [{"path": "keps/sig-x/1-a/README.md", "comments": {"nodes": [thread_comment, thread_comment]}}]}
    stats = DiscussionStats()
    rows, commented, on = build_rows(prs, threads, stats)
    assert [r["key"] for r in rows] == [
        "kubernetes/enhancements/pulls/reviews/10/body",
        "kubernetes/enhancements/pulls/comments/20",
    ]
    body, inline = rows
    assert body["author_login"] == "dom4ha" and body["source"] == "review_body" and body["path"] is None
    assert body["kind"] == "review_comment" and body["created_at_iso"] == "2025-09-23T10:07:49Z"
    assert inline["path"] == "keps/sig-x/1-a/README.md" and inline["url"].endswith("#discussion_r20")
    assert {e["to"] for e in on} == {"kubernetes/enhancements#1"}
    assert [e["from"] for e in commented] == ["dom4ha", "macsko"]
    assert stats.review_bodies == 1 and stats.thread_comments == 1 and stats.comments_seen == 5


class FakeClient:
    def __init__(self, cost: int) -> None:
        self.cost = cost
        self.cache_hits = 0
        self.calls = 0
        self.points_spent = 0

    def graphql_many(self, calls: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        return [self.graphql(q, v) for q, v in calls]

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls += 1
        self.points_spent += self.cost
        numbers = [int(n) for n in re.findall(r"\bp(\d+): pullRequest", query)]
        repo = {f"p{n}": {"number": n, "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": []}}
                for n in numbers}  # fmt: skip
        return {"rateLimit": {"cost": self.cost}, "repository": repo}


def test_budget_guard_stops_before_overspending() -> None:
    client = FakeClient(cost=10)
    stats = DiscussionStats()
    out = fetch_review_threads(cast(GitHubClient, client), list(range(1, 31)), stats, budget=25)
    assert client.calls == 2 and stats.points_spent == 20
    assert sorted(out) == list(range(1, 21)) and stats.prs_without_threads_fetched == 10
