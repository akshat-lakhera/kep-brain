"""A graph that was never written reads as empty (no 500s before the first worker run), and the
neighbourhood view renders nodes that carry no evidence id (Findings)."""

from __future__ import annotations

from typing import Any

import pytest
from falkordb import Edge, Node
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis.exceptions import ResponseError

from app.api.misc import graph_out
from app.api.routes import router
from app.db.falkordb import EMPTY, FalkorPool, QueryOutput, Role
from app.db.results import evidence_id
from app.errors import install_error_handlers
from app.settings import Settings

MISSING = "Invalid graph operation on empty key"


class _MissingGraph:
    def ro_query(self, *_: Any, **__: Any) -> Any:
        raise ResponseError(MISSING)

    def query(self, *_: Any, **__: Any) -> Any:
        raise ResponseError(MISSING)


def test_read_on_a_missing_graph_is_empty_and_a_write_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FalkorPool(Settings(falkordb_password=SecretStr("x")))
    monkeypatch.setattr(pool, "graph", lambda role, name: _MissingGraph())
    out = pool.run_sync(Role.READER, "kep", "MATCH (n) RETURN n", read_only=True, timeout_ms=100)
    assert out == EMPTY and out.rows == [] and out.as_dicts() == []
    with pytest.raises(ResponseError):
        pool.run_sync(Role.WRITER, "kep", "CREATE (n)", read_only=False, timeout_ms=100)


class EmptyPool:
    """Every read answers the empty result a missing graph now yields."""

    async def ro_query(self, graph: str, query: str, params: Any = None, timeout_ms: int = 0) -> QueryOutput:
        return EMPTY

    async def ping(self) -> list[str]:
        return []


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router, prefix="/v1")
    app.state.db = EmptyPool()
    app.state.settings = Settings()
    return TestClient(app)


@pytest.mark.parametrize(
    ("path", "empty"),
    [
        ("/v1/keps", {"items": []}),
        ("/v1/keps?q=sched", {"items": []}),
        ("/v1/keps?sig=sig-node&status=implementable", {"items": []}),
        ("/v1/sigs", {"items": []}),
        ("/v1/risk", None),
        ("/v1/findings", None),
        ("/v1/meta", None),
    ],
)
def test_list_routes_answer_empty_not_500(client: TestClient, path: str, empty: dict[str, Any] | None) -> None:
    res = client.get(path)
    assert res.status_code == 200, res.text
    if empty is not None:
        assert res.json() == empty


def test_changes_without_releases_is_a_clean_404(client: TestClient) -> None:
    res = client.get("/v1/changes")
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"


def test_findings_summary_on_an_empty_graph(client: TestClient) -> None:
    body = client.get("/v1/findings").json()
    assert body["items"] == [] and body["summary"]["total"] == 0 and body["summary"]["flagged_keps"] == 0


def test_lookups_on_an_empty_graph_are_404(client: TestClient) -> None:
    for path in ("/v1/keps/583", "/v1/sigs/sig-node", "/v1/people/alice", "/v1/graph/neighborhood?key=keps/x"):
        res = client.get(path)
        assert res.status_code == 404, (path, res.text)


KEP_KEY = "keps/sig-scheduling/268-priority-preemption"
FND_KEY = f"fnd:active_status_closed_issue:{KEP_KEY}"


def test_graph_out_includes_nodes_without_an_evidence_id() -> None:
    kep_props = {"key": KEP_KEY, "number": 268, "title": "Priority", "url": "https://github.com/k/e/tree/x/" + KEP_KEY}
    fnd_props = {"key": FND_KEY, "kind": "active_status_closed_issue", "kep_path": KEP_KEY, "source_url": "https://u"}
    kep = Node(node_id=1, labels=["KEP"], properties=kep_props)
    finding = Node(node_id=2, labels=["Finding"], properties=fnd_props)
    out = graph_out([[kep, Edge(2, "ABOUT", 1), finding]])
    ids = {n["key"]: n for n in out["nodes"]}
    assert set(ids) == {KEP_KEY, FND_KEY}
    assert ids[FND_KEY]["id"] == evidence_id("Finding", FND_KEY) and ids[FND_KEY]["label"] == "Finding"
    assert set(ids[FND_KEY]) == {"id", "label", "key", "title", "url"}
    assert out["edges"] == [{"source": ids[FND_KEY]["id"], "target": ids[KEP_KEY]["id"], "type": "ABOUT"}]
