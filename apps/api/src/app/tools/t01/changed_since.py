"""`changed_since`: status, stage and milestone changes after a release shipped, with actor and PR.

Window: changes with `at` after the release's `released_at` (the end of its
cycle). Sources: kep.yaml metadata changes (`status`, `stage`,
`latest_milestone`, `milestone.*`, from git history) and tracking-issue
milestone events. Actor: for an issue event the person who acted on it
(ACTED); for a kep.yaml change the people the derived Decision names as
author, approver, PRR approver or merger of the pull request that merged it.
Unlike `whats_changed` it leaves out label noise (lifecycle/stale, tracked/yes…)
and returns every change with its pull request.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult

FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "status": ("status",),
    "stage": ("stage",),
    "milestone": (
        "latest_milestone", "milestone.alpha", "milestone.beta", "milestone.stable", "milestone.deprecated",
        "milestone.disabled", "milestone.removed",
    ),
}  # fmt: skip

DECIDER_ROLES = ["author", "approver", "prr_approver", "merger"]

RELEASE = "MATCH (r:Release {key: $release}) RETURN r AS release, r.released_at AS t LIMIT 1"


def _changes_template(limit: int) -> str:
    return f"""
MATCH (c:StatusChange)
WHERE c.at > $t AND ((c.kind = 'metadata' AND c.field IN $fields) OR (c.kind = 'milestone' AND $issue_milestones))
MATCH (k:KEP {{key: c.kep_path}})
WHERE $sig = '' OR k.owning_sig = $sig
RETURN k AS kep, c AS change,
 [(c)-[:IN_COMMIT]->(cm:Commit)-[:IN_PR]->(pr:PullRequest) | {{commit: cm.key, pr: pr}}] AS pull_request,
 [(p:Person)-[:ACTED]->(c) | p] AS actor,
 [(c)<-[:FROM_CHANGE]-(:Decision)-[r:DECIDED_BY]->(p:Person)
   WHERE r.role IN $roles AND coalesce(p.is_bot, false) = false | {{person: p, role: r.role}}] AS deciders,
 [(i:Issue)-[:HAS_EVENT]->(c) | i] AS issue
ORDER BY c.at DESC, c.key
LIMIT {limit}
"""


CHANGES = {n: _changes_template(n) for n in (50, 100, 200)}


class ChangedSinceParams(ToolParams):
    release: str = Field(description="A shipped release, e.g. v1.36; changes after its release date are returned")
    sig: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,60}$")
    fields: list[Literal["status", "stage", "milestone"]] = Field(
        default_factory=list, description="status, stage, milestone; empty means all three"
    )
    limit: Literal[50, 100, 200] = 100

    @field_validator("release")
    @classmethod
    def _release(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"v?1\.\d{1,2}", v):
            raise ValueError("release must look like v1.36")
        return v if v.startswith("v") else "v" + v


class ChangedSince(Tool):
    name = "changed_since"
    description = (
        "Status, stage and milestone changes after a release shipped (e.g. v1.36), newest first: kep.yaml "
        "changes from git history and tracking-issue milestone events, each with from → to, date, actor "
        "(issue event actor, or the decision's author/approvers/merger) and the pull request. Optional sig "
        "and fields (status|stage|milestone). No label noise; for labels use whats_changed."
    )
    Params = ChangedSinceParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: ChangedSinceParams = params
        run = Run(ctx)
        rel = await run.query(RELEASE, {"release": p.release}, limit=2)
        if not rel:
            return run.result([{"release": p.release, "release_not_found": True}])
        release, t = rel[0]["release"], rel[0].get("t")
        if not isinstance(t, int | float):
            return run.result([{"release": release, "not_released_yet": True}])
        groups: list[str] = list(p.fields) or list(FIELD_GROUPS)
        args = {
            "t": int(t),
            "fields": [f for g in groups for f in FIELD_GROUPS[g]],
            "issue_milestones": "milestone" in groups,
            "sig": p.sig or "",
            "roles": DECIDER_ROLES,
        }
        rows = await run.query(CHANGES[p.limit], args, limit=p.limit)
        out: list[dict[str, Any]] = []
        keps: set[str] = set()
        for row in rows:
            ch, kep = row["change"], row["kep"]
            keps.add(kep["key"])
            if not row["pull_request"]:
                run.add_path(kep["key"], "CHANGED", ch["key"])
            for link in row["pull_request"]:
                run.add_path(kep["key"], "CHANGED", ch["key"], "IN_COMMIT", link["commit"], "IN_PR", link["pr"]["key"])
            for issue in row["issue"]:
                run.add_path(issue["key"], "HAS_EVENT", ch["key"])
            for person in row["actor"]:
                run.add_path(person["key"], "ACTED", ch["key"])
            out.append(
                {
                    "kep": {
                        k: kep[k] for k in ("key", "number", "title", "owning_sig", "url", "evidence_id") if k in kep
                    },  # fmt: skip
                    "change": ch,
                    "pull_request": row["pull_request"][0]["pr"] if row["pull_request"] else None,
                    "actor": row["actor"][0] if row["actor"] else None,
                    "deciders": row["deciders"],
                }
            )
        summary = {
            "release": release,
            "after": datetime.fromtimestamp(int(t), UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "changes": len(out),
            "keps": len(keps),
            "by_field": dict(Counter(str(r["change"].get("field", "")) for r in out)),
        }
        return run.result([summary, *out])
