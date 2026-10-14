"""Agent loop with a recorded provider transcript (02 §6.4 contract): validate first, then reveal."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from app.agent.loop import TOOL_RESULT_CHARS, Agent, _tool_content, fit_turn
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.provider import ToolCall, Turn, estimate_tokens
from app.db.results import Evidence, evidence_id
from app.settings import Settings
from app.tools.base import Tool, ToolContext, ToolParams, ToolResult

KEY = "keps/sig-scheduling/583-coscheduling"
EID = evidence_id("KEP", KEY)
URL = "https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/583-coscheduling"


class FakeParams(ToolParams):
    kep_ref: str


class FakeTool(Tool):
    name = "get_kep"
    description = "fake"
    Params = FakeParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        ev = Evidence(evidence_id=EID, label="KEP", key=KEY, title="KEP-583: Coscheduling", url=URL)
        row = {"label": "KEP", "key": KEY, "evidence_id": EID, "status": "provisional", "url": URL}
        return ToolResult(rows=[row], evidence=[ev], paths=[], ms=1.0, template="MATCH ...")


class Recorded:
    name = "recorded"
    model = "recorded-model"
    turns: ClassVar[list[Turn]] = []

    def __init__(self, turns: list[Turn]) -> None:
        self._turns = list(turns)

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn:
        return self._turns.pop(0)


def call(name: str, args: dict[str, Any], cid: str) -> Turn:
    raw = {"role": "assistant", "content": "", "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}  # fmt: skip
    return Turn(text="", tool_calls=[ToolCall(id=cid, name=name, arguments=args)], raw_message=raw)


def agent(turns: list[Turn]) -> Agent:
    a = Agent(pool=None, settings=Settings(llm_daily_budget_usd=100.0), provider=Recorded(turns))  # type: ignore[arg-type]
    a.tools = {"get_kep": FakeTool()}
    return a


async def run(turns: list[Turn]) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(event: str, data: dict[str, Any]) -> None:
        events.append((event, data))

    out = await agent(turns).ask("What is the status of coscheduling?", "req1", None, emit)
    return out, events


async def test_valid_transcript_reveals_validated_tokens() -> None:
    final = {"answer_markdown": f"It is provisional [[{EID}]].", "abstained": False,
             "claims": [{"text": "It is provisional", "evidence_ids": [EID]}]}  # fmt: skip
    out, events = await run([call("get_kep", {"kep_ref": "583"}, "c1"), call("final_answer", final, "c2")])
    assert not out["abstained"]
    tokens = "".join(d["text"] for e, d in events if e == "token")
    assert tokens == out["answer_markdown"] == "It is provisional [1]."
    names = [e for e, _ in events]
    assert names.index("tool_call") < names.index("citation") < names.index("token")
    assert names[-1] == "done" and out["citations"][0]["url"] == URL
    indexed = [d for e, d in events if e == "citation" and "index" in d]
    assert indexed == [{"index": 1, "evidence_id": EID, "source_type": "KEP", "title": "KEP-583: Coscheduling",
                        "locator": KEY, "url": URL}]  # fmt: skip


async def test_unseen_evidence_id_yields_no_tokens() -> None:
    final = {"answer_markdown": "It is provisional [[zzzzzzzzzzzz]].", "abstained": False,
             "claims": [{"text": "It is provisional", "evidence_ids": ["zzzzzzzzzzzz"]}]}  # fmt: skip
    out, events = await run([call("get_kep", {"kep_ref": "583"}, "c1"), call("final_answer", final, "c2")])
    assert out["abstained"] and out["abstain_reason"] == "unsupported_claims"
    assert not [e for e, _ in events if e == "token"]
    done = [d for e, d in events if e == "done"]
    assert len(done) == 1 and done[0]["abstained"] is True


async def test_no_tool_rows_abstains_no_evidence() -> None:
    final = {"answer_markdown": "Coscheduling is great.", "abstained": False, "claims": []}
    out, _ = await run([call("final_answer", final, "c1")])
    assert out["abstained"] and out["abstain_reason"] == "no_evidence" and out["answer_markdown"] == ""


async def test_invalid_params_are_reported_to_the_model() -> None:
    final = {"answer_markdown": "x", "abstained": True, "abstain_reason": "no_evidence", "claims": []}
    out, _ = await run([call("get_kep", {"wrong": 1}, "c1"), call("final_answer", final, "c2")])
    assert out["tool_calls"][0]["error"] == "invalid_params"


def test_tool_content_is_compact_json_within_the_cap() -> None:
    rows = [{"key": f"k{i}", "evidence_id": EID, "url": URL, "summary": "s" * 1000, "gate": None} for i in range(40)]
    text = _tool_content(ToolResult(rows=rows, evidence=[], paths=[], ms=1.0, template=""))
    payload = json.loads(text)
    assert len(text) <= TOOL_RESULT_CHARS and payload["rows_omitted"] >= 28
    assert "url" not in payload["rows"][0] and "gate" not in payload["rows"][0]
    assert len(payload["rows"][0]["summary"]) <= 281


def test_fit_turn_cuts_oldest_results_first() -> None:
    big = json.dumps({"rows": [{"key": f"k{i}", "text": "x" * 200} for i in range(15)]})
    messages: list[dict[str, Any]] = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    for i in range(3):
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": big})
    fit_turn(messages, [], 2000)
    assert estimate_tokens(messages) <= 2000
    assert len(messages[-1]["content"]) == len(big) and len(messages[2]["content"]) < len(big)
    json.loads(messages[2]["content"])


async def test_ask_budget_forces_the_final_answer() -> None:
    final = {"answer_markdown": f"It is provisional [[{EID}]].", "abstained": False,
             "claims": [{"text": "It is provisional", "evidence_ids": [EID]}]}  # fmt: skip
    a = agent([call("get_kep", {"kep_ref": "583"}, "c1"), call("final_answer", final, "c2")])
    seen: list[list[str]] = []
    inner = a._provider

    class Spy:
        name, model = "spy", "spy"

        async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn:
            seen.append([t["function"]["name"] for t in tools])
            return await inner.complete(messages, tools)  # type: ignore[union-attr]

    a._provider = Spy()  # type: ignore[assignment]
    # Room for the first turn only: the second (with the tool result) would pass the ask budget.
    a.ask_token_budget = estimate_tokens([{"role": "system", "content": SYSTEM_PROMPT}]) + 300
    out = await a.ask("What is the status of coscheduling?", "req2")
    assert not out["abstained"] and seen[0] != ["final_answer"] and seen[1] == ["final_answer"]
