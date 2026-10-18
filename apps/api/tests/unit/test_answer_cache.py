"""Answer cache: key stability, hit/miss behaviour in the agent loop, and the admin purge route."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_agent_loop import EID, KEY, URL, FakeTool, Recorded, answer, call

from app.agent.cache import cache_key, normalise
from app.agent.loop import Agent
from app.api import ask as ask_api
from app.db.falkordb import QueryOutput, Role
from app.db.results import Evidence, evidence_id
from app.errors import install_error_handlers
from app.settings import Settings
from app.tools.base import ToolResult


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


FINAL = f"It is provisional [[{EID}]]."


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
    out = await make_agent(pool, [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)]).ask(
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


SIG_KEY = "sig-scheduling"
SIG_EID = evidence_id("SIG", SIG_KEY)
SIG_URL = "https://github.com/kubernetes/community/tree/master/sig-scheduling"


class PathTool(FakeTool):
    """A tool whose result walks one edge: the KEP and its SIG, with the path between them."""

    async def run(self, ctx: Any, params: Any) -> Any:
        res = await super().run(ctx, params)
        sig = Evidence(evidence_id=SIG_EID, label="SIG", key=SIG_KEY, title="SIG Scheduling", url=SIG_URL)
        return ToolResult(rows=res.rows, evidence=[*res.evidence, sig], paths=[[KEY, "SPONSORED_BY", SIG_KEY]],
                          ms=res.ms, template=res.template)  # fmt: skip


async def _ask(agent: Agent, question: str, rid: str) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(event: str, data: dict[str, Any]) -> None:
        events.append((event, data))

    return await agent.ask(question, rid, None, emit), events


async def test_replay_emits_the_tool_calls_paths_and_graph_of_the_live_answer() -> None:
    pool = FakePool()
    live_agent = make_agent(pool, [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)])
    live_agent.tools = {"get_kep": PathTool()}
    live, live_events = await _ask(live_agent, "Which SIG sponsors coscheduling?", "r1")
    assert live["graph"]["edges"] == [{"source": EID, "target": SIG_EID, "type": "SPONSORED_BY"}]

    hit, events = await _ask(make_agent(pool, []), "Which SIG sponsors coscheduling?", "r2")
    # The JSON shape of a live answer (plus the cache stamp): no replay-only fields leak, templates are stripped.
    assert set(hit) == set(live) | {"cached_at"} and hit["cached"] is True and "paths" not in hit
    assert hit["graph"] == live["graph"] and hit["tool_calls"] == live["tool_calls"]
    assert all("template" not in t for t in hit["tool_calls"])
    # The SSE events a live answer produces, in order: the recorded tool call (with its template), the path it
    # read, the evidence, then the numbered citations and the checked text.
    names = [e for e, _ in events]
    assert names[:3] == ["status", "status", "tool_call"] and names[3] == "path"
    assert [d for e, d in events if e == "tool_call"] == [d for e, d in live_events if e == "tool_call"]
    assert events[2][1]["template"] == "MATCH ..."
    assert [d for e, d in events if e == "path"] == [d for e, d in live_events if e == "path"]
    assert events[3][1]["edges"] == live["graph"]["edges"]
    read = [d["evidence_id"] for e, d in events if e == "citation" and "index" not in d]
    assert set(read) == {EID, SIG_EID}
    assert names.index("path") < names.index("citation") < names.index("token") < names.index("done")
    phases = [d["phase"] for e, d in events if e == "status"]
    assert phases == ["understanding", "querying_graph", "checking", "writing"]
    assert events[-1][1] == {**events[-1][1], "nodes_read": 2, "cached": True}


async def test_an_entry_without_replay_fields_still_replays() -> None:
    """Entries cached before templates and paths were recorded: tool_call events without a template, the stored
    graph as one path event, no error."""
    pool = FakePool()
    node = {"id": EID, "label": "KEP", "key": KEY, "title": "KEP-583: Coscheduling", "url": URL}
    sig = {"id": SIG_EID, "label": "SIG", "key": SIG_KEY, "title": "SIG Scheduling", "url": SIG_URL}
    old = {
        "request_id": "r0", "question": "Which SIG sponsors coscheduling?", "answer_markdown": "SIG Scheduling [1].",
        "citations": [{"index": 1, "evidence_id": SIG_EID, "label": "SIG", "key": SIG_KEY, "title": "SIG Scheduling",
                       "url": SIG_URL}],
        "tool_calls": [{"step": 1, "name": "get_kep", "params": {"kep_ref": "583"}, "ms": 1.0, "rows": 1,
                        "truncated": False}],
        "graph": {"nodes": [node, sig], "edges": [{"source": EID, "target": SIG_EID, "type": "SPONSORED_BY"}]},
        "abstained": False, "abstain_reason": None, "latency_ms": 5, "model": "m", "findings_recalled": [],
        "memory": {"recalled": [], "remembered": []}, "usage": {"input_tokens": 1, "output_tokens": 1},
        "cached": False,
    }  # fmt: skip
    pool.rows[cache_key(old["question"], "100:5:6")] = (json.dumps(old), 7)
    hit, events = await _ask(make_agent(pool, []), old["question"], "r1")
    assert hit["cached"] is True and hit["tool_calls"] == old["tool_calls"] and hit["graph"] == old["graph"]
    assert [d for e, d in events if e == "tool_call"] == old["tool_calls"]
    assert [d for e, d in events if e == "path"] == [old["graph"]]
    assert events[-1][0] == "done" and events[-1][1]["nodes_read"] == 2

    bare = {**old, "tool_calls": [], "graph": {"nodes": [], "edges": []}}
    pool.rows[cache_key(old["question"], "100:5:6")] = (json.dumps(bare), 7)
    hit, events = await _ask(make_agent(pool, []), old["question"], "r2")
    assert hit["tool_calls"] == [] and hit["graph"] == {"nodes": [], "edges": []}
    assert not [e for e, _ in events if e in ("tool_call", "path")] and events[-1][0] == "done"


async def test_new_graph_version_misses() -> None:
    pool = FakePool()
    turns = [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)]
    await make_agent(pool, turns).ask("What is the status of coscheduling?", "r1")
    pool.version = 101
    again = [call("get_kep", {"kep_ref": "583"}, "c3"), answer(FINAL)]
    out = await make_agent(pool, again).ask("What is the status of coscheduling?", "r2")
    assert out["cached"] is False and len(pool.rows) == 2


async def test_abstained_answers_are_not_cached() -> None:
    pool = FakePool()
    abstain = answer(f"ABSTAIN: no_evidence\nNothing found [[{EID}]].")
    await make_agent(pool, [call("get_kep", {"kep_ref": "583"}, "c1"), abstain]).ask(
        "What is the status of coscheduling?", "r1"
    )
    assert not pool.rows


MEMORY_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _memory_stubs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the memory graph with a list of remembered payloads; recall finds nothing."""
    remembered: list[dict[str, Any]] = []

    async def no_recall(*_: Any) -> dict[str, Any]:
        return {"recalled": []}

    async def record(_pool: Any, memory_id: str, payload: dict[str, Any]) -> bool:
        remembered.append({"memory_id": memory_id, **payload})
        return True

    monkeypatch.setattr("app.memory.store.recall", no_recall)
    monkeypatch.setattr("app.memory.store.remember", record)
    monkeypatch.setattr("app.memory.store.planner_context", lambda _: "")
    return remembered


async def test_memory_requests_use_the_cache_and_a_hit_is_still_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()
    remembered = _memory_stubs(monkeypatch)
    turns = [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)]
    live = await make_agent(pool, turns).ask("What is the status of coscheduling?", "r1", MEMORY_ID)
    assert live["cached"] is False and len(pool.rows) == 1  # the site always sends a memory id: cache anyway
    assert live["memory"] == {"recalled": [], "remembered": ["r1"]} and [r["request_id"] for r in remembered] == ["r1"]

    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(event: str, data: dict[str, Any]) -> None:
        events.append((event, data))

    hit = await make_agent(pool, []).ask("What is the status of coscheduling?", "r2", MEMORY_ID, emit)
    assert hit["cached"] is True and hit["request_id"] == "r2"
    # The cached answer was written without this user's memory: nothing recalled, but the episode is kept.
    assert hit["memory"] == {"recalled": [], "remembered": ["r2"]}
    assert [r["request_id"] for r in remembered] == ["r1", "r2"] and remembered[-1]["memory_id"] == MEMORY_ID
    assert remembered[-1]["question"] == "What is the status of coscheduling?"
    memory_events = [d for e, d in events if e == "memory"]
    assert memory_events == [{"recalled": [], "remembered": ["r2"], "findings_recalled": []}]


async def test_memory_write_failure_never_loses_a_validated_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()

    async def boom(*_: Any) -> bool:
        raise RuntimeError("memory graph write failed")

    _memory_stubs(monkeypatch)
    monkeypatch.setattr("app.memory.store.remember", boom)
    turns = [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)]
    out = await make_agent(pool, turns).ask("What is the status of coscheduling?", "r1", MEMORY_ID)
    assert out["answer_markdown"] == "It is provisional [1]." and not out["abstained"]
    assert out["memory"] == {"recalled": [], "remembered": []}


async def test_tools_see_the_callers_memory_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []

    class SpyTool(FakeTool):
        async def run(self, ctx: Any, params: Any) -> Any:
            seen.append(ctx.memory_id)
            return await super().run(ctx, params)

    _memory_stubs(monkeypatch)
    a = make_agent(FakePool(), [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)])
    a.tools = {"get_kep": SpyTool()}
    await a.ask("What is the status of coscheduling?", "r1", MEMORY_ID)
    assert seen == [MEMORY_ID]


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


async def test_an_answer_planned_with_the_callers_memory_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool()
    _memory_stubs(monkeypatch)
    monkeypatch.setattr("app.memory.store.planner_context", lambda _: "Earlier questions of this user: ...")
    turns = [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)]
    out = await make_agent(pool, turns).ask("What is the status of coscheduling?", "r1", MEMORY_ID)
    assert out["cached"] is False and not out["abstained"] and pool.rows == {}


async def test_a_reused_request_id_is_not_reported_as_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    async def already(*_: Any) -> bool:
        return False

    _memory_stubs(monkeypatch)
    monkeypatch.setattr("app.memory.store.remember", already)
    turns = [call("get_kep", {"kep_ref": "583"}, "c1"), answer(FINAL)]
    out = await make_agent(FakePool(), turns).ask("What is the status of coscheduling?", "r1", MEMORY_ID)
    assert out["memory"]["remembered"] == []


def test_purge_with_a_non_ascii_token_is_401_not_500() -> None:
    c = admin_client(FakePool(), "s3cret")
    r = c.delete("/v1/answers/cache", headers={"Authorization": "Bearer s3cr\xe9t".encode("latin-1")})
    assert r.status_code == 401
