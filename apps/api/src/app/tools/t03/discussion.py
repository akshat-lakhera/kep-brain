"""`contested_points`: the substantive review discussion on a KEP's pull requests.

Pull requests are the ones whose commits changed the KEP's status, stage, milestones or replacement
fields (`(KEP)-[:CHANGED]->(StatusChange)-[:IN_COMMIT]->(Commit)-[:IN_PR]->(PullRequest)`). Comments
are `Comment {kind: review_comment}`: review bodies and inline review-thread comments longer than
200 characters by people (not bots), without Prow command lines. Inline comments on files of other
KEPs (a PR can touch several) are left out; review bodies are kept.
"""

from __future__ import annotations

from typing import Any, Literal

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows

_SCOPE = """
MATCH (k:KEP {key: $key})-[:CHANGED]->(:StatusChange)-[:IN_COMMIT]->(:Commit)-[:IN_PR]->(pr:PullRequest)
WITH DISTINCT k, pr
MATCH (p:Person)-[:COMMENTED]->(c:Comment {kind: 'review_comment'})-[:ON]->(pr)
WHERE (c.path IS NULL OR c.path STARTS WITH (k.path + '/')) AND coalesce(p.is_bot, false) = false
"""


def _comments_template(limit: int) -> str:
    return f"""{_SCOPE}
RETURN c AS comment, p AS person, pr AS pull_request, c.excerpt AS excerpt, c.source AS source, c.path AS path,
 c.created_at_iso AS created_at_iso, c.url AS url
ORDER BY c.created_at, c.key
LIMIT {limit}
"""


COMMENTS = {n: _comments_template(n) for n in (20, 50, 100)}

SUMMARY = f"""{_SCOPE}
WITH pr, p, c
RETURN count(c) AS comments, count(DISTINCT pr) AS pull_requests, count(DISTINCT p) AS people,
 min(c.created_at_iso) AS first_iso, max(c.created_at_iso) AS last_iso
"""

AUTHORS = f"""{_SCOPE}
RETURN p.login AS login, p.url AS url, count(c) AS comments
ORDER BY comments DESC, login
LIMIT 10
"""


class ContestedPointsParams(ToolParams):
    kep_ref: KepRef
    limit: Literal[20, 50, 100] = 50


class ContestedPoints(Tool):
    name = "contested_points"
    description = (
        "The substantive review discussion on a KEP's pull requests (the PRs that changed its status, stage or "
        "milestones): review bodies and inline review comments longer than 200 characters by people, oldest "
        "first, each with author, date, the PR, the file it was on, a 600-character excerpt and its GitHub URL. "
        "rows[0] counts comments, PRs and people and lists the most active reviewers. Use for 'who objected', "
        "'what was debated', 'what concerns were raised' about a KEP."
    )
    Params = ContestedPointsParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: ContestedPointsParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        args = {"key": res.key}
        summary_rows = await run.query(SUMMARY, args, limit=2)
        authors = await run.query(AUTHORS, args, limit=11)
        rows = await run.query(COMMENTS[p.limit], args, limit=p.limit)
        kep = res.candidates[0]
        out: list[dict[str, Any]] = []
        for row in rows:
            comment, person, pr = row["comment"], row["person"], row["pull_request"]
            run.add_path(person["key"], "COMMENTED", comment["key"], "ON", pr["key"])
            out.append(
                {
                    "at_iso": row.get("created_at_iso"),
                    "author": {"login": person.get("login"), "url": person.get("url"),
                               "evidence_id": person.get("evidence_id")},
                    "source": row.get("source"),
                    "path": row.get("path"),
                    "pull_request": {"number": pr.get("number"), "title": pr.get("title"), "url": pr.get("url"),
                                     "evidence_id": pr.get("evidence_id")},
                    "excerpt": row.get("excerpt"),
                    "url": row.get("url"),
                    "evidence_id": comment.get("evidence_id"),
                }
            )  # fmt: skip
        summary = summary_rows[0] if summary_rows else {}
        head = {
            "kep": {k: kep[k] for k in ("key", "number", "title", "url", "evidence_id") if k in kep},
            "comments": int(summary.get("comments") or 0),
            "pull_requests": int(summary.get("pull_requests") or 0),
            "people": int(summary.get("people") or 0),
            "first_iso": summary.get("first_iso"),
            "last_iso": summary.get("last_iso"),
            "top_commenters": authors,
            "shown": len(out),
        }
        return run.result([head, *out])
