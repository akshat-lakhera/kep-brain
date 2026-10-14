"""Answer cache: key stability, hit/miss behaviour in the agent loop, and the admin purge route."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_agent_loop import EID, FakeTool, Recorded, call

from app.agent.cache import AnswerCache, cache_key, normalise
from app.agent.loop import Agent
from app.api import ask as ask_api
from app.db.falkordb import QueryOutput, Role
from app.errors import install_error_handlers
from app.settings import Settings


class FakePool:
    """Stands in for FalkorPool: one AnswerCache table in a dict, one fixed graph version."""

    def __init__(self, version: int = 100) -> None:
        self.version = version
        self.rows: dict[str, tuple[str, int]] = {}
        self.roles: list[Role] = []

    async def ro_query(self, graph: str, query: str, params: Any = None, timeout_ms: int = 0) -> QueryOutput:
        return QueryOutput(["a", "b", "c"], [[self.version, 5, 6]], 0.0, {})

    async def ping(self) -> list[str]:
        return []

    async def write(self, role: Role, graph: str, query: str, params: Any = None, timeout_ms: int = 0) -> QueryOutput:
        if graph != "ops":
            return QueryOutput([], [], 0.0, {})
        self.roles.append(role)
        if query.startswith("MATCH (c:AnswerCache {key"):
            hit = self.rows.get(params["key"])
            return QueryOutput(["r", "t"], [[hit[0], hit[1]]] if hit else [], 0.0, {})
        if query.startswith("MERGE"):
            self.rows[params["key"]] = (params["response"], params["now"])
            return QueryOutput([], [], 0.0, {})
        deleted = len(self.rows)
        self.rows.clear()
        return QueryOutput([], [], 0.0, {"nodes_deleted": deleted})


FINAL = {"answer_markdown": f"It is provisional [[{EID}]].", "abstained": False,
         "claims": [{"text": "It is provisional", "evidence_ids": [EID]}]}  # fmt: skip


def make_agent(pool: FakePool, turns: list[Any]) -> Agent:
    a = Agent(pool=pool, settings=Settings(llm_daily_budget_usd=100.0), provider=Recorded(turns))  # type: ignore[arg-type]
    a.tools = {"get_kep": FakeTool()}
    return a


def test_key_ignores_case_spacing_and_trailing_punctuation_but_not_version() -> None:
    assert normalise("  What IS  KEP-1?? ") == "what is kep-1"
    assert cache_key("What is KEP-1?", "v1") == cache_key("what is   kep-1", "v1")
    assert cache_key("What is KEP-1?", "v1") != cache_key("What is KEP-1?", "v2")


async def test_second_ask_is_served_from_the_cache_with_replayed_events() -> None:
    pool = FakePool()
    out = await make_agent(pool, [call("get_kep", {"kep_ref": "583"}, "c1"), call("final_answer", FINAL, "c2")]).ask(
        "What is the status of coscheduling?", "r1"
    )
    assert out["cached"] is False and len(pool.rows) == 1 and set(pool.roles) == {Role.OPS}
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(event: str, data: dict[str, Any]) -> None:
        events.append((event, data))

    hit = await make_agent(pool, []).ask("what is the status of  coscheduling", "r2", None, emit)
    assert hit["cached"] is True and hit["cached_at"] > 0 and hit["request_id"] == "r2"
    assert hit["answer_markdown"] == out["answer_markdown"] and hit["usage"]["input_tokens"] == 0
    assert "".join(d["text"] for e, d in events if e == "token") == out["answer_markdown"]
    assert events[-1][0] == "done" and events[-1][1]["cached"] is True
    assert any(e == "citation" and d.get("index") == 1 for e, d in events)


async def test_new_graph_version_misses() -> None:
    pool = FakePool()
    turns = [call("get_kep", {"kep_ref": "583"}, "c1"), call("final_answer", FINAL, "c2")]
    await make_agent(pool, turns).ask("What is the status of coscheduling?", "r1")
    pool.version = 101
    again = [call("get_kep", {"kep_ref": "583"}, "c3"), call("final_answer", FINAL, "c4")]
    out = await make_agent(pool, again).ask("What is the status of coscheduling?", "r2")
    assert out["cached"] is False and len(pool.rows) == 2


async def test_abstained_answers_and_memory_requests_are_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()
    abstain = {"answer_markdown": "x", "abstained": True, "abstain_reason": "no_evidence", "claims": []}
    await make_agent(pool, [call("get_kep", {"kep_ref": "583"}, "c1"), call("final_answer", abstain, "c2")]).ask(
        "What is the status of coscheduling?", "r1"
    )
    assert not pool.rows

    async def no_recall(*_: Any) -> dict[str, Any]:
        return {"recalled": []}

    async def no_remember(*_: Any) -> None:
        return None

    monkeypatch.setattr("app.memory.store.recall", no_recall)
    monkeypatch.setattr("app.memory.store.remember", no_remember)
    monkeypatch.setattr("app.memory.store.planner_context", lambda _: "")
    turns = [call("get_kep", {"kep_ref": "583"}, "c1"), call("final_answer", FINAL, "c2")]
    a = make_agent(pool, turns)
    a.cache = AnswerCache(pool)  # type: ignore[arg-type]
    await a.ask("What is the status of coscheduling?", "r2", "01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert not pool.rows


def admin_client(pool: FakePool, token: str | None) -> TestClient:
    from pydantic import SecretStr

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(ask_api.router, prefix="/v1")
    app.state.db = pool
    app.state.settings = Settings(admin_token=SecretStr(token) if token else None)
    return TestClient(app)


def test_purge_requires_the_admin_token() -> None:
    pool = FakePool()
    pool.rows["k"] = (json.dumps({}), 1)
    c = admin_client(pool, "s3cret")
    assert c.delete("/v1/answers/cache").status_code == 401
    assert c.delete("/v1/answers/cache", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert pool.rows
    ok = c.delete("/v1/answers/cache", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200 and ok.json() == {"deleted": 1} and not pool.rows
    no_token = admin_client(pool, None).delete("/v1/answers/cache", headers={"Authorization": "Bearer x"})
    assert no_token.status_code == 401
