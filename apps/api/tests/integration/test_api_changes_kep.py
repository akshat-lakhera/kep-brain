"""GET /v1/changes* against the loaded `kep` graph at the pinned data (read-only)."""

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


def test_default_since_latest_shipped_release(client: TestClient) -> None:
    body = client.get("/v1/changes").json()
    assert body["since"] == "v1.37"
    assert body["window"] == {"start_iso": "2026-05-05T16:03:21Z", "basis": "tracking_issue_milestone"}
    assert body["releases"][0] == "v1.1" and body["releases"][-1] == "v1.41" and len(body["releases"]) == 41
    counts = body["counts"]
    assert counts["keps_changed"] >= 96 and counts["status_transitions"] >= 47 and counts["new_keps"] >= 27
    items = body["items"]
    assert len(items) == 200
    assert [i["at_iso"] for i in items] == sorted((i["at_iso"] for i in items), reverse=True)
    assert all(i["source_url"].startswith("https://github.com/kubernetes/") for i in items)
    assert {i["kind"] for i in items} <= {"metadata", "label", "milestone"}


def test_since_v136_scheduling(client: TestClient) -> None:
    body = client.get("/v1/changes", params={"since": "v1.36", "sig": "sig-scheduling", "limit": 500}).json()
    assert body["window"]["start_iso"] == "2026-01-09T15:09:53Z"
    assert all(i["owning_sig"] == "sig-scheduling" for i in body["items"])
    status = [i for i in body["items"] if i["kind"] == "metadata" and i["field"] == "status"]
    assert len(status) == body["counts"]["status_transitions"] >= 1
    assert all(i["pr"] is None or i["pr"]["url"].startswith("https://github.com/kubernetes/enhancements/pull/")
               for i in body["items"])  # fmt: skip


def test_unknown_release_and_meta_releases(client: TestClient) -> None:
    assert client.get("/v1/changes", params={"since": "v2.0"}).status_code == 404
    assert client.get("/v1/meta").json()["releases"][-5:] == ["v1.37", "v1.38", "v1.39", "v1.40", "v1.41"]
