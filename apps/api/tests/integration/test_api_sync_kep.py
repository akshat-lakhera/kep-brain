"""GET /v1/sync* against the loaded `kep` graph at the pinned data (read-only)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.falkordb import GRAPH_KEP, FalkorPool, Role
from app.main import create_app
from app.settings import Settings


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    pool = FalkorPool(Settings())
    try:
        loaded = (
            GRAPH_KEP in pool.list_graphs()
            and pool.run_sync(
                Role.READER, GRAPH_KEP, "MATCH (k:KEP) RETURN count(k)", read_only=True, timeout_ms=2000
            ).rows[0][0]
            >= 238
        )
    except Exception:  # noqa: BLE001
        loaded = False
    finally:
        pool.close()
    if not loaded:
        pytest.skip("graph `kep` is not loaded at the pinned data")
    with TestClient(create_app()) as c:
        yield c


def test_sync_status(client: TestClient) -> None:
    body = client.get("/v1/sync/status").json()
    assert body["pinned"] == {
        "enhancements_sha": "8659e382efab7340d70de52432ee8f3d9979b797",
        "community_sha": "53c338ecba4a2a9240f6654cca1d6a9dac25c785",
    }
    assert body["tickets_as_of"]
    assert body["counts_by_label"]["KEP"] == 238 and body["counts_by_label"]["Finding"] >= 59
    run = body["last_run"]
    assert run is None or (isinstance(run["ok"], bool) and isinstance(run["steps"], dict))
    assert set(body) == {"pinned", "tickets_as_of", "last_run", "counts_by_label", "worker_last_seen_iso",
                         "next_tick_iso"}  # fmt: skip
