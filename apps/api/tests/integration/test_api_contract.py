"""HTTP contract against the real `kep` graph (read-only); skipped when the graph has no KEPs."""

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
        graphs = pool.list_graphs()
        has_keps = (
            GRAPH_KEP in graphs
            and pool.run_sync(
                Role.READER, GRAPH_KEP, "MATCH (k:KEP) RETURN count(k)", read_only=True, timeout_ms=2000
            ).rows[0][0]
        )
    except Exception:  # noqa: BLE001
        has_keps = 0
    finally:
        pool.close()
    if not has_keps:
        pytest.skip("graph `kep` has no data")
    with TestClient(create_app()) as c:
        yield c


def test_meta(client: TestClient) -> None:
    body = client.get("/v1/meta").json()
    assert body["graph"]["keps"] > 200 and set(body["llm"]) == {"provider", "model", "configured"}


def test_kep_list_and_card_shape(client: TestClient) -> None:
    items = client.get("/v1/keps", params={"q": "gang scheduling", "limit": 5}).json()["items"]
    assert items and set(items[0]) == {
        "key", "number", "title", "owning_sig", "status", "stage", "latest_milestone", "url", "open_findings",
    }  # fmt: skip
    assert len(client.get("/v1/keps", params={"sig": "sig-node", "limit": 300}).json()["items"]) > 50


def test_kep_detail_and_ambiguity(client: TestClient) -> None:
    detail = client.get("/v1/keps/4671").json()
    for field in ("milestones", "authors", "prr_approvers", "feature_gates", "relations", "sections", "findings"):
        assert field in detail
    assert {r["number"] for r in detail["relations"]["replaces"]} >= {583}
    amb = client.get("/v1/keps/2133")
    assert amb.status_code == 409 and len(amb.json()["error"]["details"]["candidates"]) == 2
    path = amb.json()["error"]["details"]["candidates"][0]["key"]
    assert client.get("/v1/keps/2133", params={"path": path}).status_code == 200
    assert client.get("/v1/keps/999999").status_code == 404


def test_history_decisions_findings(client: TestClient) -> None:
    hist = client.get("/v1/keps/1287/history").json()["items"]
    assert hist and all("at_iso" in h for h in hist)
    assert "items" in client.get("/v1/keps/1287/decisions").json()
    f = client.get("/v1/findings").json()
    assert set(f["summary"]) == {"flagged_keps", "total", "by_kind", "by_sig"}


def test_tools_and_graph(client: TestClient) -> None:
    tools = client.get("/v1/tools").json()["items"]
    assert len(tools) == 14
    r = client.post("/v1/tools/get_kep", json={"kep_ref": 583}).json()
    assert set(r) == {"rows", "evidence", "paths", "truncated", "ms", "template"}
    assert client.post("/v1/tools/get_kep", json={"kep_ref": "x; DROP"}).status_code == 422
    assert client.post("/v1/tools/nope", json={}).status_code == 404
    g = client.get("/v1/graph/neighborhood", params={"key": "keps/sig-scheduling/4671-gang-scheduling"}).json()
    assert g["nodes"] and g["edges"] and {"source", "target", "type"} <= set(g["edges"][0])


def test_eval_and_board(client: TestClient) -> None:
    qs = client.get("/v1/eval/questions").json()["questions"]
    assert [q["id"] for q in qs][:1] == ["STA-04"]
    assert client.get("/v1/agents/board").status_code == 200
    assert client.get("/v1/memory/me").status_code == 400
