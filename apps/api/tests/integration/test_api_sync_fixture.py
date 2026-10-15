"""Worker run records (app.worker.runs) and GET /v1/sync/status against throwaway graphs."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from fixture_graph import STATEMENTS

from app.db.falkordb import FalkorPool, Role
from app.main import create_app
from app.settings import Settings
from app.worker.runs import RunRecorder, heartbeat, iso

GRAPH = "test_api2_sync_kep"
OPS = "test_api2_sync_ops"


@pytest.fixture(scope="module")
def pool() -> Iterator[FalkorPool]:
    p = FalkorPool(Settings())
    try:
        graphs = p.list_graphs()
    except Exception:  # noqa: BLE001
        pytest.skip("FalkorDB not reachable")
    for g in (GRAPH, OPS):
        if g in graphs:
            p.graph(Role.WRITER, g).delete()
    for stmt in STATEMENTS:
        p.run_sync(Role.WRITER, GRAPH, stmt, read_only=False, timeout_ms=10000)
    yield p
    for g in (GRAPH, OPS):
        if g in p.list_graphs():
            p.graph(Role.WRITER, g).delete()
    p.close()


@pytest.fixture(scope="module")
def client(pool: FalkorPool) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        c.app.state.kep_graph = GRAPH  # type: ignore[attr-defined]
        c.app.state.ops_graph = OPS  # type: ignore[attr-defined]
        yield c


def test_status_without_runs(client: TestClient) -> None:
    body = client.get("/v1/sync/status").json()
    assert body["last_run"] is None and body["worker_last_seen_iso"] is None and body["next_tick_iso"] is None
    assert body["counts_by_label"]["KEP"] == 6 and body["counts_by_label"]["Person"] == 3
    assert body["pinned"]["enhancements_sha"] == Settings().enhancements_pin_sha


def test_recorded_runs_and_heartbeat(pool: FalkorPool, client: TestClient) -> None:
    ok = RunRecorder(pool, "01TESTRUNA", "all", GRAPH, ops_graph=OPS)
    ok.start()
    ok.step("schema-apply", lambda: {"created": 2, "existing": 40})
    ok.step("sync-docs", lambda: {"keps": 6})
    ok.step("stats", lambda: {})
    ok.finish(ok=True)
    nxt = int(time.time()) + 900
    heartbeat(pool, nxt, ops_graph=OPS)

    body = client.get("/v1/sync/status").json()
    run = body["last_run"]
    assert run["ok"] is True and run["started_at_iso"] and run["finished_at_iso"]
    assert {k: v["count"] for k, v in run["steps"].items()} == {"schema-apply": 42, "sync-docs": 6, "stats": 20}
    assert all(isinstance(v["ms"], int) for v in run["steps"].values())
    assert body["next_tick_iso"] == iso(nxt) and body["worker_last_seen_iso"]

    failed = RunRecorder(pool, "01TESTRUNB", "all", GRAPH, ops_graph=OPS)
    failed.start()
    with pytest.raises(RuntimeError):
        failed.step("sync-docs", _boom)
    failed.finish(ok=False, error="RuntimeError: clone missing")
    run = client.get("/v1/sync/status").json()["last_run"]
    assert run["ok"] is False and run["steps"] == {} and "error" not in run
    stored = pool.run_sync(
        Role.READER, OPS, "MATCH (r:SyncRun {key: '01TESTRUNB'}) RETURN r.error", read_only=True, timeout_ms=2000
    )
    assert stored.rows[0][0] == "RuntimeError: clone missing"


def _boom() -> dict[str, int]:
    raise RuntimeError("clone missing")
