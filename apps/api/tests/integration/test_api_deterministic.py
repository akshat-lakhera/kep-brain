"""Deterministic (non-LLM) HTTP endpoints against the loaded `kep` graph at the pinned data; read-only."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from conftest import live_graph_pinned
from fastapi.testclient import TestClient

from app.db.falkordb import FalkorPool
from app.main import create_app
from app.mcp.__main__ import build_app
from app.settings import Settings

FINDING_KINDS = 5
FINDINGS_TOTAL = 59
FLAGGED_KEPS = 50


def _graph_loaded() -> bool:
    pool = FalkorPool(Settings())
    try:
        return live_graph_pinned(pool, "MATCH (f:Finding) RETURN count(f)", FINDINGS_TOTAL)
    except Exception:  # noqa: BLE001
        return False
    finally:
        pool.close()


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    if not _graph_loaded():
        pytest.skip("graph `kep` is not loaded at the pinned data")
    with TestClient(create_app()) as c:
        yield c


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200 and res.json() == {"status": "ok"}


def test_meta_sources(client: TestClient) -> None:
    body = client.get("/v1/meta").json()
    assert body["sources"]["community_sha"]
    assert body["sources"]["tickets_as_of"]
    assert body["graph"]["findings"] == FINDINGS_TOTAL


@pytest.mark.parametrize(
    ("number", "history_len"),
    [(583, 20), (1287, 210), (4671, 75)],
)
def test_kep_detail_and_history(client: TestClient, number: int, history_len: int) -> None:
    detail = client.get(f"/v1/keps/{number}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["number"] == number and body["title"] and body["url"].startswith("https://github.com/")
    history = client.get(f"/v1/keps/{number}/history").json()["items"]
    assert len(history) == history_len
    assert [h["at_iso"] for h in history] == sorted(h["at_iso"] for h in history)


def test_kep_4671_replaces_583(client: TestClient) -> None:
    body = client.get("/v1/keps/4671").json()
    assert 583 in {r["number"] for r in body["relations"]["replaces"]}


def test_findings_summary(client: TestClient) -> None:
    body = client.get("/v1/findings").json()
    summary = body["summary"]
    assert summary["total"] == FINDINGS_TOTAL == len(body["items"])
    assert summary["flagged_keps"] == FLAGGED_KEPS
    assert len(summary["by_kind"]) == FINDING_KINDS
    assert sum(summary["by_kind"].values()) == FINDINGS_TOTAL


def test_draft_stale_doc_issue_is_deterministic(client: TestClient) -> None:
    items = client.get("/v1/findings").json()["items"]
    finding = min(items, key=lambda i: i["key"])
    first = client.post("/v1/tools/draft_stale_doc_issue", json={"finding_key": finding["key"]})
    second = client.post("/v1/tools/draft_stale_doc_issue", json={"finding_key": finding["key"]})
    assert first.status_code == 200
    draft = first.json()["rows"][0]
    assert draft["finding_key"] == finding["key"]
    assert draft["posted"] is False and draft["status"] == "drafted"
    assert draft["target_repo"] == "kubernetes/enhancements"
    assert finding["a_url"] in draft["body"] and finding["b_url"] in draft["body"]
    assert draft["title"].startswith(f"KEP-{finding['kep_number']}:")
    assert second.json()["rows"][0] == draft


async def test_mcp_requires_bearer_token() -> None:
    pool = FalkorPool(Settings())
    try:
        app = build_app(Settings(mcp_token="test-token-not-real"), pool)  # type: ignore[arg-type]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8001") as http:
            missing = await http.post("/mcp", json={})
            wrong = await http.post("/mcp", json={}, headers={"Authorization": "Bearer nope"})
    finally:
        pool.close()
    assert missing.status_code == 401 and missing.headers["www-authenticate"] == "Bearer"
    assert wrong.status_code == 401
