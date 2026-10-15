"""Sync status card (05 §4.3.3): pinned sources, the last recorded worker run, node counts and heartbeat.

Runs and the heartbeat are written by the worker into the `ops` graph (`app.worker.runs`); with no
run recorded yet `last_run` is null and the heartbeat fields are null. A failed run's error text stays in
the ops graph; the public card shows only `ok`.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import graph_of, ops_graph_of, pool_of, rows_of, settings_of
from app.api.misc import source_pins

router = APIRouter(tags=["sync"])

LAST_RUN = """
MATCH (r:SyncRun)
RETURN r.started_at_iso AS started_at_iso, r.finished_at_iso AS finished_at_iso, r.ok AS ok,
 r.steps_json AS steps_json
ORDER BY r.started_at DESC, r.key DESC
LIMIT 1
"""

HEARTBEAT = """
MATCH (h:WorkerHeartbeat {key: 'worker'})
RETURN h.last_seen_iso AS last_seen_iso, h.next_tick_iso AS next_tick_iso
LIMIT 1
"""

LABEL_COUNTS = "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n ORDER BY label"


def _steps(raw: Any) -> dict[str, dict[str, int]]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(name): {"count": int(v.get("count", 0)), "ms": int(v.get("ms", 0))}
        for name, v in data.items()
        if isinstance(v, dict)
    }


@router.get("/sync/status")
async def sync_status(request: Request) -> dict[str, Any]:
    pool, settings = pool_of(request), settings_of(request)
    graph, ops = graph_of(request), ops_graph_of(request)
    graphs = await pool.ping()
    pins: dict[str, str | None] = {
        "enhancements_sha": settings.enhancements_pin_sha,
        "community_sha": settings.community_pin_sha,
        "tickets_as_of": settings.tickets_as_of,
    }
    counts: dict[str, int] = {}
    if graph in graphs:
        pins = await source_pins(pool, settings, graph)
        out = await pool.ro_query(graph, LABEL_COUNTS, timeout_ms=5000)
        counts = {str(label): int(n) for label, n in out.rows}

    last_run = None
    beat: dict[str, Any] = {}
    if ops in graphs:
        runs = rows_of(await pool.ro_query(ops, LAST_RUN))
        if runs:
            r = runs[0]
            last_run = {
                "started_at_iso": r["started_at_iso"],
                "finished_at_iso": r["finished_at_iso"],
                "ok": bool(r["ok"]),
                "steps": _steps(r["steps_json"]),
            }
        beats = rows_of(await pool.ro_query(ops, HEARTBEAT))
        beat = beats[0] if beats else {}

    return {
        "pinned": {"enhancements_sha": pins["enhancements_sha"], "community_sha": pins["community_sha"]},
        "tickets_as_of": pins["tickets_as_of"],
        "last_run": last_run,
        "counts_by_label": counts,
        "worker_last_seen_iso": beat.get("last_seen_iso"),
        "next_tick_iso": beat.get("next_tick_iso"),
    }
