"""Sync-run records in the `ops` graph, read by `GET /v1/sync/status`.

One `SyncRun {key: <sync_run_id>}` node per `all` run (one-shot or scheduled): start and finish
times, `ok`, `error`, `current_step`, and per step `{count, ms, state, started_at_iso, finished_at_iso,
detail}` stored as JSON in `steps_json` (FalkorDB has no map properties). The node is updated when a
step starts and when it ends, so a run in progress shows its current step; `ok` is absent (null)
until the run finishes. A step's `count` is the number of nodes of the label that step loads, counted in
the target graph once the step has finished (index entries for `schema-apply`, all nodes for
`stats`). The `schedule` loop also keeps one `WorkerHeartbeat {key: 'worker'}` node with the time
the worker was last seen and the time of its next tick.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from app.db.falkordb import GRAPH_OPS, WRITE_TIMEOUT_MS, FalkorPool, Role
from app.ingest.common import iso

HEARTBEAT_KEY = "worker"
STEP_LABELS = {
    "sync-docs": "KEP",
    "sync-history": "Commit",
    "sync-owners": "OwnersFile",
    "sync-tickets": "Issue",
    "derive": "Decision",
}

START = """
MERGE (r:SyncRun {key: $key})
SET r.command = $command, r.graph = $graph, r.started_at = $at, r.started_at_iso = $at_iso,
 r.steps_json = '{}', r.observed_at = $at
REMOVE r.ok, r.finished_at, r.finished_at_iso, r.error, r.current_step
"""

PROGRESS = """
MATCH (r:SyncRun {key: $key})
SET r.steps_json = $steps, r.current_step = $current, r.observed_at = $at
"""

FINISH = """
MATCH (r:SyncRun {key: $key})
SET r.finished_at = $at, r.finished_at_iso = $at_iso, r.ok = $ok, r.steps_json = $steps, r.observed_at = $at
REMOVE r.current_step
"""

SET_ERROR = "MATCH (r:SyncRun {key: $key}) SET r.error = $error"

BEAT = """
MERGE (h:WorkerHeartbeat {key: $key})
SET h.last_seen = $at, h.last_seen_iso = $at_iso, h.next_tick = $next, h.next_tick_iso = $next_iso, h.observed_at = $at
"""


def _write(pool: FalkorPool, ops_graph: str, query: str, params: dict[str, Any]) -> None:
    pool.run_sync(Role.OPS, ops_graph, query, params, read_only=False, timeout_ms=WRITE_TIMEOUT_MS)


class RunRecorder:
    def __init__(self, pool: FalkorPool, run_id: str, command: str, graph: str, ops_graph: str = GRAPH_OPS) -> None:
        self.pool = pool
        self.run_id = run_id
        self.command = command
        self.graph = graph
        self.ops_graph = ops_graph
        self.steps: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        now = int(time.time())
        _write(self.pool, self.ops_graph, START, {
            "key": self.run_id, "command": self.command, "graph": self.graph, "at": now, "at_iso": iso(now),
        })  # fmt: skip

    def _progress(self, current: str) -> None:
        _write(self.pool, self.ops_graph, PROGRESS, {
            "key": self.run_id, "steps": json.dumps(self.steps), "current": current, "at": int(time.time()),
        })  # fmt: skip

    def step(self, name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        started = time.monotonic()
        entry: dict[str, Any] = {"count": 0, "ms": 0, "state": "running", "started_at_iso": iso(int(time.time()))}
        self.steps[name] = entry
        self._progress(name)
        try:
            result = fn()
        except Exception:
            self.steps.pop(name, None)  # a failed step is reported by the run's `ok` and error, not as a step
            raise
        ms = int((time.monotonic() - started) * 1000)
        entry.update(count=self._count(name, result), ms=ms, state="done", finished_at_iso=iso(int(time.time())),
                     detail=_detail(result))  # fmt: skip
        self._progress(name)
        return result

    def finish(self, ok: bool, error: str | None = None) -> None:
        now = int(time.time())
        _write(self.pool, self.ops_graph, FINISH, {
            "key": self.run_id, "at": now, "at_iso": iso(now), "ok": ok, "steps": json.dumps(self.steps),
        })  # fmt: skip
        if error:
            _write(self.pool, self.ops_graph, SET_ERROR, {"key": self.run_id, "error": error[:500]})

    def _count(self, name: str, result: dict[str, Any]) -> int:
        if name == "schema-apply":
            return int(result.get("created", 0)) + int(result.get("existing", 0))
        label = STEP_LABELS.get(name)
        query = f"MATCH (n:{label}) RETURN count(n)" if label else "MATCH (n) RETURN count(n)"
        out = self.pool.run_sync(Role.READER, self.graph, query, read_only=True, timeout_ms=WRITE_TIMEOUT_MS)
        return int(out.rows[0][0]) if out.rows else 0


def _detail(result: dict[str, Any]) -> dict[str, int]:
    """Integer counters a step reported (one level deep), for the status card."""
    out: dict[str, int] = {}
    for k, v in result.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            out[str(k)] = v
        elif isinstance(v, dict):
            out.update({f"{k}.{kk}": vv for kk, vv in v.items() if isinstance(vv, int) and not isinstance(vv, bool)})
    return dict(list(out.items())[:24])


def heartbeat(pool: FalkorPool, next_tick: int | None, ops_graph: str = GRAPH_OPS) -> None:
    now = int(time.time())
    _write(pool, ops_graph, BEAT, {
        "key": HEARTBEAT_KEY, "at": now, "at_iso": iso(now), "next": next_tick,
        "next_iso": iso(next_tick) if next_tick is not None else None,
    })  # fmt: skip
