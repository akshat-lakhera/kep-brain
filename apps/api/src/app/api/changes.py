"""Changes since a release (05 §4.3.2).

"Since release X" starts at the first event that introduced X as a milestone value:

1. the earliest tracking-issue milestone event that set milestone X (`StatusChange{kind: milestone,
   to_value: X}`): the enhancements team opting the first KEP into X's cycle;
2. if no issue was ever milestoned X, the earliest kep.yaml commit that set `latest_milestone` or a
   `milestone.*` field to X;
3. if X never appears as a milestone value, the release node's first appearance in the graph
   (`Release.first_seen_at`).

Every StatusChange at or after that instant is in the window. `changed_since` (Track 1 tool) is not
reused: it starts at the release's ship date, which leaves out the release's own cycle.

Items: kep.yaml changes to status, stage, latest_milestone, milestone.*, replaces and superseded_by
(`metadata`), tracking-issue milestone events (`milestone`), and tracking-issue label events for the
enhancement-tracking labels stage/* and lead-opted-in (`label`; lifecycle, sig and triage label noise
is left out). Automation labels (`app.tools.noise`: tracked/*, lgtm, approved, cncf-cla*, size/*) are left
out unless `include_labels=true`. `actor_login` is the event's actor for issue events and the author of the
pull request that merged the kep.yaml change otherwise. Default `since`: the latest shipped release
(the graph also holds planned future releases, which have no cycle yet).

Counts cover the whole window (not only the returned page): `status_transitions` and `stage_changes`
count kep.yaml status and stage changes, `milestone_changes` counts kep.yaml milestone changes plus
issue milestone events, `label_changes` counts the label events in the window (same label filter as the
items), `new_keps` counts KEPs whose first kep.yaml change falls in the window.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps import graph_of, pool_of, rows_of, variant_for
from app.db.falkordb import FalkorPool
from app.errors import AppError
from app.ingest.common import iso
from app.tools.noise import automation_label_predicate

router = APIRouter(tags=["changes"])

MILESTONE_FIELDS = [
    "latest_milestone", "milestone.alpha", "milestone.beta", "milestone.stable", "milestone.deprecated",
    "milestone.disabled", "milestone.removed",
]  # fmt: skip
METADATA_FIELDS = ["status", "stage", *MILESTONE_FIELDS, "replaces", "superseded_by"]
TRACKING_LABELS = ["tracked/yes", "tracked/no", "tracked/out-of-tree", "lead-opted-in"]
LIMITS = (50, 100, 200, 500)

RELEASES = "MATCH (r:Release) RETURN r.key AS key, r.ordinal AS ordinal, r.is_future AS is_future"

RELEASE = "MATCH (r:Release {key: $release}) RETURN r.first_seen_at AS first_seen_at LIMIT 1"

ISSUE_START = """
MATCH (c:StatusChange {kind: 'milestone'})
WHERE c.to_value = $release
RETURN min(c.at) AS t
"""

KEP_YAML_START = """
MATCH (c:StatusChange {kind: 'metadata'})
WHERE c.to_value = $release AND c.field IN $milestone_fields
RETURN min(c.at) AS t
"""

IN_WINDOW = f"""c.at >= $t AND (
  (c.kind = 'metadata' AND c.field IN $metadata_fields)
  OR c.kind = 'milestone'
  OR (c.kind = 'label' AND (c.field STARTS WITH 'stage/' OR c.field IN $tracking_labels)
      AND ($include_labels OR NOT {automation_label_predicate()})))"""


def _items_template(limit: int) -> str:
    return f"""
MATCH (c:StatusChange)
WHERE {IN_WINDOW}
MATCH (k:KEP {{key: c.kep_path}})
WHERE $sig = '' OR k.owning_sig = $sig
OPTIONAL MATCH (c)-[:IN_COMMIT]->(:Commit)-[:IN_PR]->(pr:PullRequest)
WITH c, k, collect(pr)[0] AS pr
RETURN k.number AS kep_number, k.title AS kep_title, k.owning_sig AS owning_sig, c.kind AS kind, c.field AS field,
 c.from_value AS from_value, c.to_value AS to_value, c.at_iso AS at_iso,
 coalesce(c.actor_login, pr.author_login) AS actor_login,
 CASE WHEN pr IS NULL THEN NULL ELSE {{number: pr.number, url: pr.url}} END AS pr,
 c.source_url AS source_url
ORDER BY c.at DESC, c.key
LIMIT {limit}
"""


ITEMS = {n: _items_template(n) for n in LIMITS}

COUNTS = f"""
MATCH (c:StatusChange)
WHERE {IN_WINDOW}
MATCH (k:KEP {{key: c.kep_path}})
WHERE $sig = '' OR k.owning_sig = $sig
RETURN count(DISTINCT k) AS keps_changed,
 sum(CASE WHEN c.kind = 'metadata' AND c.field = 'status' THEN 1 ELSE 0 END) AS status_transitions,
 sum(CASE WHEN c.kind = 'metadata' AND c.field = 'stage' THEN 1 ELSE 0 END) AS stage_changes,
 sum(CASE WHEN c.kind = 'milestone' OR (c.kind = 'metadata' AND c.field IN $milestone_fields) THEN 1 ELSE 0 END)
   AS milestone_changes,
 sum(CASE WHEN c.kind = 'label' THEN 1 ELSE 0 END) AS label_changes
"""

NEW_KEPS = """
MATCH (k:KEP)-[:CHANGED]->(c:StatusChange {kind: 'metadata'})
WHERE $sig = '' OR k.owning_sig = $sig
WITH k, min(c.at) AS first
WHERE first >= $t
RETURN count(k) AS new_keps
"""


def _release_order(row: dict[str, Any]) -> tuple[int, int]:
    m = re.fullmatch(r"v(\d+)\.(\d+)", str(row["key"]))
    return (int(m.group(1)), int(m.group(2))) if m else (0, int(row.get("ordinal") or 0))


async def release_keys(pool: FalkorPool, graph: str) -> list[str]:
    """Every Release in the graph, ascending by version."""
    rows = rows_of(await pool.ro_query(graph, RELEASES))
    return [r["key"] for r in sorted(rows, key=_release_order)]


async def window_start(pool: FalkorPool, graph: str, release: str) -> tuple[int, str] | None:
    """(epoch seconds, basis) for the start of "since `release`" (module docstring); None if unknown."""
    args = {"release": release, "milestone_fields": MILESTONE_FIELDS}
    for basis, query in (("tracking_issue_milestone", ISSUE_START), ("kep_yaml_milestone", KEP_YAML_START)):
        rows = (await pool.ro_query(graph, query, args)).rows
        if rows and rows[0][0] is not None:
            return int(rows[0][0]), basis
    rows = (await pool.ro_query(graph, RELEASE, args)).rows
    if rows and rows[0][0] is not None:
        return int(rows[0][0]), "release_first_seen"
    return None


async def default_since(pool: FalkorPool, graph: str) -> str | None:
    """The latest shipped release (highest `Release` with is_future = false); the second-highest release
    in the graph when no release is marked shipped."""
    rows = rows_of(await pool.ro_query(graph, RELEASES))
    shipped = sorted((r for r in rows if r.get("is_future") is False), key=_release_order)
    if shipped:
        return str(shipped[-1]["key"])
    ordered = [r["key"] for r in sorted(rows, key=_release_order)]
    return ordered[-2] if len(ordered) >= 2 else (ordered[-1] if ordered else None)


@router.get("/changes")
async def list_changes(
    request: Request,
    since: str | None = Query(default=None, max_length=12),
    sig: str = Query(default="", max_length=60),
    limit: int = Query(default=200, ge=1, le=500),
    include_labels: bool = Query(default=False),
) -> dict[str, Any]:
    pool, graph = pool_of(request), graph_of(request)
    releases = await release_keys(pool, graph)
    if since is None:
        since = await default_since(pool, graph)
    else:
        since = since.strip()
        if re.fullmatch(r"1\.\d{1,2}", since):
            since = "v" + since
    if since is None or since not in releases:
        raise AppError("not_found", {"since": (since or "")[:20], "releases": releases})
    start = await window_start(pool, graph, since)
    if start is None:
        raise AppError("not_found", {"since": since, "reason": "no window start for this release"})
    t, basis = start
    args = {
        "t": t,
        "sig": sig,
        "metadata_fields": METADATA_FIELDS,
        "milestone_fields": MILESTONE_FIELDS,
        "tracking_labels": TRACKING_LABELS,
        "include_labels": include_labels,
    }
    variant = variant_for(limit, LIMITS)
    items = rows_of(await pool.ro_query(graph, ITEMS[variant], args, timeout_ms=5000))[:limit]
    counts_rows = rows_of(await pool.ro_query(graph, COUNTS, args, timeout_ms=5000))
    new_rows = rows_of(await pool.ro_query(graph, NEW_KEPS, args, timeout_ms=5000))
    counts = {k: int(counts_rows[0].get(k) or 0) if counts_rows else 0
              for k in ("keps_changed", "status_transitions", "stage_changes", "milestone_changes",
                        "label_changes")}  # fmt: skip
    counts["new_keps"] = int(new_rows[0]["new_keps"]) if new_rows else 0
    return {
        "since": since,
        "include_labels": include_labels,
        "window": {"start_iso": iso(int(t)), "basis": basis},
        "releases": releases,
        "counts": counts,
        "items": items,
    }
