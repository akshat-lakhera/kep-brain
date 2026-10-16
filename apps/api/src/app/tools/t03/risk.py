"""`knowledge_risk` (tool) and `GET /v1/risk`: where decision knowledge sits with too few people.

Active KEPs are those whose kep.yaml status is not terminal (`TERMINAL_STATUSES`). Approvers are the
current `(Person)-[:APPROVES]->(KEP)` edges from kep.yaml (bots left out).

- `single_approver`: active KEPs with exactly one approver.
- `load`: the people approving the most active KEPs, with their share of all active KEPs.
- `idle`: people who approve or author an active KEP and have no `DECIDED_BY` edge (any role) on a
  Decision since the window start: the release date of the shipped release before the last two, so
  the window covers the last two release cycles. People with no decision at all are idle too.

Every row carries the KEP's and the person's GitHub URLs and the kep.yaml URL the approver edge
came from.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import Field

from app.ingest.common import iso
from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult

TERMINAL_STATUSES = ["implemented", "withdrawn", "replaced", "rejected"]
LOAD_LIMIT = 10
IDLE_LIMIT = 200
IDLE_RELEASES = 2

QueryFn = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

ACTIVE = "NOT k.status IN $terminal AND ($sig = '' OR k.owning_sig = $sig)"
HUMAN = "coalesce(p.is_bot, false) = false"

SHIPPED = """
MATCH (r:Release)
WHERE r.is_future = false AND r.released_at IS NOT NULL
RETURN r.key AS release, r.released_at AS released_at
ORDER BY r.released_at DESC
LIMIT 3
"""

COUNTS = f"""
MATCH (k:KEP)
WHERE {ACTIVE}
OPTIONAL MATCH (p:Person)-[r:APPROVES]->(k)
WHERE r.valid_to = $open AND {HUMAN}
WITH k, count(DISTINCT p) AS approvers
RETURN count(k) AS active_keps, sum(CASE WHEN approvers = 0 THEN 1 ELSE 0 END) AS without_approver,
 sum(CASE WHEN approvers = 1 THEN 1 ELSE 0 END) AS single_approver
"""

SINGLE = f"""
MATCH (k:KEP)
WHERE {ACTIVE}
MATCH (p:Person)-[r:APPROVES]->(k)
WHERE r.valid_to = $open AND {HUMAN}
WITH k, collect(DISTINCT p) AS ps, collect(r.source_url) AS sources
WHERE size(ps) = 1
WITH k, ps[0] AS p, sources[0] AS source_url
RETURN k AS _kep, p AS _person, k.number AS kep_number, k.title AS kep_title, k.owning_sig AS owning_sig,
 k.status AS status, k.stage AS stage, k.url AS kep_url, p.login AS approver, p.url AS approver_url, source_url
ORDER BY owning_sig, kep_number
LIMIT 200
"""

LOAD = f"""
MATCH (k:KEP)
WHERE {ACTIVE}
MATCH (p:Person)-[r:APPROVES]->(k)
WHERE r.valid_to = $open AND {HUMAN}
WITH p, collect(DISTINCT k.number) AS keps
RETURN p AS _person, p.login AS login, p.url AS url, size(keps) AS active_keps, keps
ORDER BY active_keps DESC, login
LIMIT {LOAD_LIMIT}
"""

IDLE = f"""
MATCH (k:KEP)
WHERE {ACTIVE}
MATCH (p:Person)-[r:APPROVES|AUTHORED]->(k)
WHERE coalesce(r.valid_to, $open) = $open AND {HUMAN}
WITH p, collect(DISTINCT k.number) AS keps, collect(DISTINCT type(r)) AS rels
OPTIONAL MATCH (d:Decision)-[:DECIDED_BY]->(p)
WITH p, keps, rels, max(d.decided_at) AS last
WHERE last IS NULL OR last < $idle_since
RETURN p AS _person, p.login AS login, p.url AS url, last AS last_decision, size(keps) AS active_keps, keps, rels
ORDER BY active_keps DESC, login
LIMIT {IDLE_LIMIT}
"""


def _iso(epoch: Any) -> str | None:
    if not isinstance(epoch, int | float):
        return None
    return iso(int(epoch))


def idle_window(shipped: list[dict[str, Any]]) -> tuple[int, str] | None:
    """(start epoch, basis) for the idle window: the release date of the shipped release before the last two."""
    if not shipped:
        return None
    ordered = sorted(shipped, key=lambda r: int(r["released_at"]), reverse=True)
    base = ordered[min(IDLE_RELEASES, len(ordered) - 1)]
    covered = ", ".join(str(r["release"]) for r in ordered[:IDLE_RELEASES])
    return int(base["released_at"]), f"released_at of {base['release']} (start of the {covered} cycles)"


def _role(rels: list[str]) -> list[str]:
    return sorted({"approver" if r == "APPROVES" else "author" for r in rels})


async def knowledge_risk(query: QueryFn, sig: str | None) -> dict[str, Any]:
    """Assemble the risk report from the fixed templates (`query(template, params)` returns row dicts)."""
    base = {"terminal": TERMINAL_STATUSES, "sig": sig or ""}
    shipped = await query(SHIPPED, {})
    window = idle_window(shipped)
    idle_since = window[0] if window else 0
    counts_rows = await query(COUNTS, base)
    counts = counts_rows[0] if counts_rows else {}
    active_total = int(counts.get("active_keps") or 0)
    single = await query(SINGLE, base)
    load = await query(LOAD, base)
    idle = await query(IDLE, {**base, "idle_since": idle_since})
    return {
        "sig": sig,
        "counts": {
            "active_keps": active_total,
            "single_approver": int(counts.get("single_approver") or 0),
            "without_approver": int(counts.get("without_approver") or 0),
            "idle_people": len(idle),
        },
        "single_approver": [
            {
                "kep": {"number": r["kep_number"], "title": r["kep_title"], "owning_sig": r["owning_sig"],
                        "status": r["status"], "stage": r.get("stage"), "url": r["kep_url"]},
                "approver": {"login": r["approver"], "url": r["approver_url"]},
                "source_url": r.get("source_url"),
            }
            for r in single
        ],
        "load": [
            {
                "login": r["login"],
                "url": r["url"],
                "active_keps": int(r["active_keps"]),
                "share": round(int(r["active_keps"]) / active_total, 3) if active_total else 0.0,
                "keps": sorted(int(n) for n in r["keps"] if n is not None),
            }
            for r in load
        ],
        "idle": [
            {
                "login": r["login"],
                "url": r["url"],
                "last_decision_iso": _iso(r.get("last_decision")),
                "active_keps": int(r["active_keps"]),
                "keps": sorted(int(n) for n in r["keps"] if n is not None),
                "roles": _role(list(r.get("rels") or [])),
            }
            for r in idle
        ],
        "thresholds": {
            "terminal_statuses": TERMINAL_STATUSES,
            "approver_source": "current APPROVES edges from kep.yaml approvers; bots excluded",
            "load_limit": LOAD_LIMIT,
            "idle_since_iso": _iso(idle_since) if window else None,
            "idle_basis": window[1] if window else "no shipped release with a release date",
            "idle_roles": ["approver", "author"],
            "idle_limit": IDLE_LIMIT,
        },
    }  # fmt: skip


class KnowledgeRiskParams(ToolParams):
    sig: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,60}$", description="e.g. sig-node; empty = all")


class KnowledgeRisk(Tool):
    name = "knowledge_risk"
    description = (
        "Knowledge at risk on active (not implemented/withdrawn/replaced/rejected) KEPs: KEPs with exactly one "
        "kep.yaml approver, the people approving the most active KEPs (with their share), and approvers or "
        "authors of active KEPs with no recorded decision in the last two release cycles. Optional sig. "
        "Use for 'bus factor', 'who is overloaded', 'which KEPs depend on one person'."
    )
    Params = KnowledgeRiskParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: KnowledgeRiskParams = params
        run = Run(ctx)

        async def query(template: str, args: dict[str, Any]) -> list[dict[str, Any]]:
            rows = await run.query(template, args, limit=10_000)
            for row in rows:
                kep, person = row.get("_kep"), row.get("_person")
                if isinstance(kep, dict) and isinstance(person, dict):
                    run.add_path(person["key"], "APPROVES", kep["key"])
            return rows

        report = await knowledge_risk(query, p.sig)
        rows: list[dict[str, Any]] = [{"sig": p.sig, "counts": report["counts"], "thresholds": report["thresholds"]}]
        rows += [{"kind": "single_approver", **r} for r in report["single_approver"]]
        rows += [{"kind": "load", **r} for r in report["load"]]
        rows += [{"kind": "idle", **r} for r in report["idle"]]
        return run.result(rows)
