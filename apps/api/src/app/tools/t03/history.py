"""Tools 8 `trace_decision`, 9 `status_history`, 10 `whats_changed` (03 §15.1, §7, §8.2)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows

DecisionKind = Literal[
    "status_transition", "stage_graduation", "milestone_retarget", "prr_approval", "replacement", "withdrawal"
]


def _trace_template(limit: int) -> str:
    return f"""
MATCH (d:Decision {{kep_path: $key}})
WHERE size($kinds) = 0 OR d.kind IN $kinds
WITH d ORDER BY d.decided_at, d.key LIMIT {limit}
RETURN d AS decision,
 [(d)-[r:DECIDED_BY]->(p:Person) | {{person: p, role: r.role}}] AS people,
 [(d)-[r:EVIDENCED_BY]->(e) | {{node: e, evidence_kind: r.evidence_kind}}] AS evidence,
 [(d)-[:FROM_CHANGE]->(c:StatusChange) | c] AS change,
 [(d)-[:FROM_CHANGE]->(:StatusChange)-[:IN_COMMIT]->(cm:Commit) | cm] AS commits,
 [(d)-[:FROM_CHANGE]->(:StatusChange)-[:IN_COMMIT]->(:Commit)-[:IN_PR]->(pr:PullRequest) | pr] AS pull_requests
ORDER BY d.decided_at, d.key
"""


TRACE = {n: _trace_template(n) for n in (10, 20, 50)}


class TraceDecisionParams(ToolParams):
    kep_ref: KepRef
    kinds: list[DecisionKind] = Field(default_factory=list, description="Decision kinds; empty means all")
    limit: Literal[10, 20, 50] = 20


class TraceDecision(Tool):
    name = "trace_decision"
    description = (
        "Why and by whom a KEP's state changed: the derived Decision nodes in time order, each with the people "
        "who decided (role: author, merger, approver, prr_approver…), the evidence (pull request, reviews, "
        "/approve comments, commit), the underlying status change (field, from → to, date), the commit and the "
        "pull request that merged it. Use for 'when was X marked implemented, by whom, in which PR'."
    )
    Params = TraceDecisionParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: TraceDecisionParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        rows = await run.query(TRACE[p.limit], {"key": res.key, "kinds": p.kinds}, limit=p.limit)
        for row in rows:
            dk = row["decision"]["key"]
            run.add_path(dk, "ABOUT", res.key)
            for person in row.get("people", []):
                run.add_path(dk, "DECIDED_BY", person["person"]["key"])
            for ev in row.get("evidence", []):
                run.add_path(dk, "EVIDENCED_BY", ev["node"]["key"])
        if not rows:
            rows = [{"kep": res.candidates[0], "decisions": 0}]
        return run.result(rows)


HISTORY_TEMPLATE = """
MATCH (c:StatusChange {kep_path: $key})
WHERE (size($fields) = 0 OR c.field IN $fields) AND ($labels OR c.kind = 'metadata')
RETURN c AS change,
 [(c)-[:IN_COMMIT]->(cm:Commit) | cm] AS commit,
 [(c)-[:IN_COMMIT]->(:Commit)-[:IN_PR]->(pr:PullRequest) | pr] AS pull_request,
 [(p:Person)-[:ACTED]->(c) | p] AS actor
ORDER BY c.at, c.seq, c.key
LIMIT 200
"""

CURRENT_TEMPLATE = """
MATCH (k:KEP {key: $key})
RETURN k AS kep,
 [(k)-[r:TRACKED_BY]->(i:Issue) WHERE coalesce(r.valid_to, $open) = $open | i] AS tracking_issue
LIMIT 1
"""


class StatusHistoryParams(ToolParams):
    kep_ref: KepRef
    fields: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Fields such as status, stage, latest_milestone, milestone.beta, label, milestone; empty = all",
    )
    include_label_events: bool = True

    @field_validator("fields")
    @classmethod
    def _fields(cls, v: list[str]) -> list[str]:
        for f in v:
            if not re.fullmatch(r"[a-z_.\-]{2,40}", f):
                raise ValueError("invalid field name")
        return v


class StatusHistory(Tool):
    name = "status_history"
    description = (
        "The full timeline of a KEP's metadata (kep.yaml status, stage, milestones, from git history) interleaved "
        "with the tracking issue's label and milestone events, ordered by time. Each change has from → to, date, "
        "actor, is_reversal, the commit and the pull request. Also returns the current KEP card and tracking "
        "issue. Use for reversals ('was it ever moved back?') and 'when did X change'."
    )
    Params = StatusHistoryParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: StatusHistoryParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        current = await run.query(CURRENT_TEMPLATE, {"key": res.key}, limit=2)
        changes = await run.query(
            HISTORY_TEMPLATE, {"key": res.key, "fields": p.fields, "labels": p.include_label_events}, limit=200
        )
        for ch in changes:
            run.add_path(res.key, "CHANGED", ch["change"]["key"])
            for cm in ch.get("commit", []):
                run.add_path(ch["change"]["key"], "IN_COMMIT", cm["key"])
        rows: list[dict[str, Any]] = [{"current": current[0] if current else None, "changes": len(changes)}]
        rows.extend(changes)
        return run.result(rows)


RELEASE_TEMPLATE = "MATCH (r:Release {key: $release}) RETURN r LIMIT 1"


def _changed_template(limit: int) -> str:
    return f"""
MATCH (c:StatusChange)
WHERE c.at >= $t AND (size($kinds) = 0 OR c.kind IN $kinds) AND (size($fields) = 0 OR c.field IN $fields)
MATCH (k:KEP {{key: c.kep_path}})
WHERE $sig = '' OR k.owning_sig = $sig
RETURN k AS kep, c AS change
ORDER BY c.at DESC, c.key
LIMIT {limit}
"""


CHANGED = {n: _changed_template(n) for n in (50, 100, 200)}

DECISIONS_SINCE = """
MATCH (d:Decision)
WHERE d.decided_at >= $t
MATCH (k:KEP {key: d.kep_path})
WHERE $sig = '' OR k.owning_sig = $sig
RETURN k AS kep, d AS decision
ORDER BY d.decided_at DESC, d.key
LIMIT 100
"""


class WhatsChangedParams(ToolParams):
    since: str = Field(description="A release such as v1.35, or an ISO date such as 2026-01-01")
    sig: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,60}$")
    kinds: list[Literal["metadata", "label", "milestone"]] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list, max_length=10)
    limit: Literal[50, 100, 200] = 100

    @field_validator("since")
    @classmethod
    def _since(cls, v: str) -> str:
        v = v.strip()
        if re.fullmatch(r"v?1\.\d{1,2}", v):
            return v if v.startswith("v") else "v" + v
        try:
            datetime.fromisoformat(v)
        except ValueError as exc:
            raise ValueError("since must be a release (v1.35) or an ISO date (2026-01-01)") from exc
        return v


class WhatsChanged(Tool):
    name = "whats_changed"
    description = (
        "What changed across the corpus since a release (uses its release date) or an ISO date: status changes "
        "(kep.yaml metadata, issue labels and milestones) grouped by KEP, newest first, plus derived decisions "
        "in the window. Optional sig filter (e.g. sig-node) and kinds filter (metadata|label|milestone)."
    )
    Params = WhatsChangedParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: WhatsChangedParams = params
        run = Run(ctx)
        if p.since.startswith("v"):
            rel = await run.query(RELEASE_TEMPLATE, {"release": p.since}, limit=2)
            released = rel[0]["r"] if rel else None
            if not rel:
                return run.result([{"since": p.since, "release_not_found": True}])
            t = await self._release_time(run, p.since)
            if t is None:
                return run.result([{"since": p.since, "release": released, "release_date_unknown": True}])
        else:
            dt = datetime.fromisoformat(p.since)
            t = int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp())
        args = {"t": t, "kinds": list(p.kinds), "fields": p.fields, "sig": p.sig or ""}
        changes = await run.query(CHANGED[p.limit], args, limit=p.limit)
        decisions = await run.query(DECISIONS_SINCE, {"t": t, "sig": p.sig or ""}, limit=100)
        by_kep: dict[str, dict[str, Any]] = {}
        for row in changes:
            entry = by_kep.setdefault(row["kep"]["key"], {"kep": row["kep"], "changes": [], "decisions": []})
            entry["changes"].append(row["change"])
            run.add_path(row["kep"]["key"], "CHANGED", row["change"]["key"])
        for row in decisions:
            entry = by_kep.setdefault(row["kep"]["key"], {"kep": row["kep"], "changes": [], "decisions": []})
            entry["decisions"].append(row["decision"])
        since_iso = datetime.fromtimestamp(t, UTC).isoformat()
        summary = {
            "since": p.since,
            "since_at_iso": since_iso,
            "keps_changed": len(by_kep),
            "changes_shown": len(changes),
            "status_transitions": sum(1 for r in changes if r["change"].get("field") == "status"),
        }
        return run.result([summary, *by_kep.values()])

    async def _release_time(self, run: Run, release: str) -> int | None:
        rows = await run.query(
            "MATCH (r:Release {key: $release}) RETURN r.released_at AS t LIMIT 1", {"release": release}, limit=2
        )
        value = rows[0].get("t") if rows else None
        if isinstance(value, int | float):
            return int(value)
        if isinstance(value, str) and value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp())
        return None
