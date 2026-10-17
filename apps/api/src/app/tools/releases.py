"""Where "since release X" starts, shared by the changes API and the `whats_changed` tool.

A release's window opens with the first event that introduced X as a milestone value:

1. the earliest tracking-issue milestone event that set milestone X: the enhancements team opting the
   first KEP into X's cycle;
2. if no issue was ever milestoned X, the earliest kep.yaml commit that set `latest_milestone` or a
   `milestone.*` field to X;
3. if X never appears as a milestone value: for a shipped release its ship date, and when even that is
   unknown the whole history (a release older than every record means "everything"); for a planned release
   the moment it first appeared in the graph.

This covers the release's own cycle, so "since v1.38" works while v1.38 is still being built, and
"since v1.1" means every change on record rather than nothing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

MILESTONE_FIELDS = [
    "latest_milestone", "milestone.alpha", "milestone.beta", "milestone.stable", "milestone.deprecated",
    "milestone.disabled", "milestone.removed",
]  # fmt: skip

RELEASE_FALLBACK = (
    "MATCH (r:Release {key: $release}) "
    "RETURN r.first_seen_at AS first_seen, r.released_at AS released, coalesce(r.is_future, false) AS is_future LIMIT 1"
)

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

Query = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def window_start(query: Query, release: str) -> tuple[int, str] | None:
    """(epoch seconds, basis) for the start of "since `release`"; None when the graph does not know it.

    `query` runs one read-only Cypher statement and returns its rows as dicts with a `t` column.
    """
    args = {"release": release, "milestone_fields": MILESTONE_FIELDS}
    for basis, statement in (("tracking_issue_milestone", ISSUE_START), ("kep_yaml_milestone", KEP_YAML_START)):
        rows = await query(statement, args)
        value = rows[0].get("t") if rows else None
        if isinstance(value, int | float):
            return int(value), basis
    rows = await query(RELEASE_FALLBACK, args)
    if not rows:
        return None
    row = rows[0]
    if row.get("is_future"):
        seen = row.get("first_seen")
        return (int(seen), "release_first_seen") if isinstance(seen, int | float) else None
    released = row.get("released")
    if isinstance(released, int | float):
        return int(released), "release_date"
    return 0, "all_history"
