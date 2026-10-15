"""Sync status card (05 §4.3.3): pinned sources, the last recorded worker run, node counts and heartbeat.

Runs and the heartbeat are written by the worker into the `ops` graph (`app.worker.runs`); with no
run recorded yet `last_run` is null and the heartbeat fields are null. A failed run's error text stays in
the ops graph; the public card shows only `ok`.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import graph_of, ops_graph_of, pool_of, rows_of, settings_of
from app.api.misc import source_pins

router = APIRouter(tags=["sync"])

LAST_RUN = """
MATCH (r:SyncRun)
RETURN r.started_at_iso AS started_at_iso, r.finished_at_iso AS finished_at_iso, r.ok AS ok,
 r.steps_json AS steps_json, r.current_step AS current_step, r.observed_at AS observed_at
ORDER BY r.started_at DESC, r.key DESC
LIMIT 1
"""

HEARTBEAT = """
MATCH (h:WorkerHeartbeat {key: 'worker'})
RETURN h.last_seen_iso AS last_seen_iso, h.next_tick_iso AS next_tick_iso
LIMIT 1
"""

LABEL_COUNTS = "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n ORDER BY label"


# A run whose record has not changed for this long is a worker that died, not one in progress.
RUNNING_STALE_SECONDS = 3 * 3600


def _steps(raw: Any) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, v in data.items():
        if not isinstance(v, dict):
            continue
        step: dict[str, Any] = {"count": int(v.get("count", 0)), "ms": int(v.get("ms", 0))}
        for extra in ("state", "started_at_iso", "finished_at_iso", "detail"):
            if extra in v:
                step[extra] = v[extra]
        out[str(name)] = step
    return out


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
            finished = r["finished_at_iso"] is not None
            seen = r["observed_at"]
            alive = isinstance(seen, int) and time.time() - seen < RUNNING_STALE_SECONDS
            # `ok` is null while the run is in progress (no finish time yet and the record is fresh).
            running = not finished and alive and r["ok"] is None
            last_run = {
                "started_at_iso": r["started_at_iso"],
                "finished_at_iso": r["finished_at_iso"],
                "ok": None if running else bool(r["ok"]),
                "steps": _steps(r["steps_json"]),
            }
            if running:
                last_run["current_step"] = r["current_step"]
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
