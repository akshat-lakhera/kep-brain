"""GET /v1/changes* against the loaded `kep` graph at the pinned data (read-only)."""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from conftest import live_graph_pinned
from fastapi.testclient import TestClient

from app.db.falkordb import FalkorPool
from app.main import create_app
from app.settings import Settings


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    pool = FalkorPool(Settings())
    try:
        loaded = live_graph_pinned(pool)
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
    meta = client.get("/v1/meta").json()
    # The default window starts at the latest shipped release, whichever that is when the graph was synced.
    assert body["since"] in body["releases"] and body["releases"] == meta["releases"]
    minors = [int(r.split(".")[1]) for r in body["releases"]]
    assert minors == sorted(minors) and body["releases"][0] == "v1.1" and body["since"] != body["releases"][-1]
    assert re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z", body["window"]["start_iso"])
    assert body["window"]["basis"] == "tracking_issue_milestone"
    counts = body["counts"]
    assert counts["keps_changed"] >= 96 and counts["status_transitions"] >= 47 and counts["new_keps"] >= 27
    items = body["items"]
    assert len(items) == 200
    assert [i["at_iso"] for i in items] == sorted((i["at_iso"] for i in items), reverse=True)
    assert all(i["source_url"].startswith("https://github.com/kubernetes/") for i in items)
    assert {i["kind"] for i in items} <= {"metadata", "label", "milestone"}


def test_since_v136_scheduling(client: TestClient) -> None:
    body = client.get("/v1/changes", params={"since": "v1.36", "sig": "sig-scheduling", "limit": 500}).json()
    assert re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z", body["window"]["start_iso"])
    assert all(i["owning_sig"] == "sig-scheduling" for i in body["items"])
    status = [i for i in body["items"] if i["kind"] == "metadata" and i["field"] == "status"]
    assert len(status) == body["counts"]["status_transitions"] >= 1
    assert all(i["pr"] is None or i["pr"]["url"].startswith("https://github.com/kubernetes/enhancements/pull/")
               for i in body["items"])  # fmt: skip


def test_unknown_release_and_meta_releases(client: TestClient) -> None:
    assert client.get("/v1/changes", params={"since": "v2.0"}).status_code == 404
    releases = client.get("/v1/meta").json()["releases"]
    assert len(releases) >= 5 and all(r.startswith("v1.") for r in releases[-5:])
