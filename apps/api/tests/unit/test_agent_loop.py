"""Agent loop with a recorded provider transcript (02 §6.4 contract): validate first, then reveal."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from app.agent.loop import MIN_RESULT_CHARS, TOOL_RESULT_CHARS, Agent, _tool_content, fit_rows, fit_turn
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.provider import ToolCall, Turn, estimate_tokens
from app.agent.validator import link_mentions, parse_answer
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


def answer(text: str) -> Turn:
    return Turn(text=text, raw_message={"role": "assistant", "content": text})


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
    out, events = await run([call("get_kep", {"kep_ref": "583"}, "c1"), answer(f"It is provisional [[{EID}]].")])
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
    out, events = await run([call("get_kep", {"kep_ref": "583"}, "c1"), answer("It is provisional [[zzzzzzzzzzzz]].")])
    assert out["abstained"] and out["abstain_reason"] == "unsupported_claims"
    assert not [e for e, _ in events if e == "token"]
    done = [d for e, d in events if e == "done"]
    assert len(done) == 1 and done[0]["abstained"] is True


async def test_no_tool_rows_abstains_no_evidence() -> None:
    out, _ = await run([answer("Coscheduling is great.")])
    assert out["abstained"] and out["abstain_reason"] == "no_evidence" and out["answer_markdown"] == ""


async def test_invalid_params_are_reported_to_the_model() -> None:
    out, _ = await run([call("get_kep", {"wrong": 1}, "c1"), answer("ABSTAIN: no_evidence\nNothing found.")])
    assert out["tool_calls"][0]["error"] == "invalid_params"


def test_tool_content_is_compact_json_within_the_cap() -> None:
    rows = [{"key": f"k{i}", "evidence_id": EID, "url": URL, "summary": "s" * 1000, "gate": None} for i in range(40)]
    text = _tool_content(ToolResult(rows=rows, evidence=[], paths=[], ms=1.0, template=""))
    payload = json.loads(text)
    assert len(text) <= TOOL_RESULT_CHARS and payload["rows_omitted"] >= 28
    assert "url" not in payload["rows"][0] and "gate" not in payload["rows"][0]
    assert len(payload["rows"][0]["summary"]) <= 281


def test_fit_turn_shares_the_budget_and_keeps_small_results_whole() -> None:
    big = json.dumps({"rows": [{"key": f"k{i}", "text": "x" * 200} for i in range(15)]})
    small = json.dumps({"rows": [{"key": "k", "status": "provisional"}]})
    messages: list[dict[str, Any]] = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    for i, content in enumerate([big, small, big, big]):
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": content})
    fit_turn(messages, [], 2000)
    assert estimate_tokens(messages) <= 2000
    tool = [m["content"] for m in messages if m["role"] == "tool"]
    assert tool[1] == small
    bigs = [len(tool[i]) for i in (0, 2, 3)]
    assert max(bigs) < len(big) and max(bigs) - min(bigs) < 300
    for content in tool:
        json.loads(content)


def test_fit_turn_leaves_a_fitting_turn_alone() -> None:
    messages = [{"role": "user", "content": "q"}, {"role": "tool", "tool_call_id": "c", "content": "x" * 500}]
    fit_turn(messages, [], 2000)
    assert messages[1]["content"] == "x" * 500 and MIN_RESULT_CHARS < 500


def test_fit_rows_drops_descriptive_fields_before_rows() -> None:
    rows = [{"kep": {"key": f"keps/sig-x/{i}-k", "evidence_id": f"{EID[:-1]}{i + 2}", "status": "implementable",
                     "title": "A long descriptive title " * 4, "labels_current": ["a/b", "c/d"]}}
            for i in range(4)]  # fmt: skip
    full = json.dumps({"rows": rows}, separators=(",", ":"))
    payload = json.loads(fit_rows({"rows": rows}, len(full) // 2))
    assert len(payload["rows"]) == 4 and payload["fields_cut"] and "rows_omitted" not in payload
    assert all("title" not in r["kep"] and r["kep"]["status"] == "implementable" for r in payload["rows"])


def test_path_next_to_via_edges_is_not_repeated() -> None:
    row = {"path": ["a", "REPLACES", "b"], "via": [{"type": "REPLACES", "from": "a", "to": "b"}]}
    only_path = {"path": ["a", "PRR_APPROVED", "b"]}
    payload = json.loads(_tool_content(ToolResult(rows=[row, only_path], evidence=[], paths=[], ms=1.0, template="")))
    assert "path" not in payload["rows"][0] and payload["rows"][1]["path"] == ["a", "PRR_APPROVED", "b"]


def test_parse_answer_reads_abstention_and_claims_from_text() -> None:
    a = parse_answer(f"**ABSTAIN: no_evidence**\nNo gate has that name; KEP-4671 declares GenericWorkload [[{EID}]].")
    assert a.abstained and a.abstain_reason == "no_evidence" and a.answer_markdown.startswith("No gate")
    assert [c.evidence_ids for c in a.claims] == [[EID]]
    b = parse_answer(f"Status:\n\n1. provisional [[{EID}]]\n2. issue closed [[{EID}, zzzzzzzzzzzz]]")
    assert not b.abstained and [c.evidence_ids for c in b.claims] == [[EID], [EID, "zzzzzzzzzzzz"]]
    c = parse_answer("ABSTAIN: There is nothing about this.")
    assert c.abstained and c.abstain_reason == "no_evidence" and c.answer_markdown == "There is nothing about this."


async def test_long_answers_are_kept_whole() -> None:
    text = "\n".join(f"{i}. fact number {i} " + "x" * 120 + f" [[{EID}]]" for i in range(1, 8))
    out, _ = await run([call("get_kep", {"kep_ref": "583"}, "c1"), answer(text)])
    assert not out["abstained"] and len(out["answer_markdown"]) > 900 and out["answer_markdown"].endswith("[1]")


def test_link_mentions_cites_explicit_references_to_returned_records() -> None:
    def ev(label: str, key: str) -> Evidence:
        return Evidence(evidence_id=evidence_id(label, key), label=label, key=key, title=key, url=URL)

    records = [ev("KEP", KEY), ev("Issue", "kubernetes/enhancements#583"), ev("Person", "soltysh"),
               ev("Finding", f"fnd:active_status_closed_issue:{KEY}")]  # fmt: skip
    evidence = {e.evidence_id: e for e in records}
    kep, issue, person = (records[i].evidence_id for i in range(3))
    text = (f"**KEP‑583** is provisional [[{kep}]]; issue #583 closed.\n"
            "Approved by @soltysh, see `kubernetes/enhancements#583`; KEP-9999 and #12 are unknown.")  # fmt: skip
    linked = link_mentions(text, evidence).split("\n")
    assert linked[0] == f"**KEP‑583** is provisional [[{kep}]]; issue #583 [[{issue}]] closed."
    assert linked[1] == (
        f"Approved by @soltysh [[{person}]], see `kubernetes/enhancements#583`; KEP-9999 and #12 are unknown."
    )


async def test_markers_without_an_evidence_id_are_removed() -> None:
    text = f"It is provisional [[{EID}]]. It is stale [[fnd:active_status_closed_issue:{KEY}]]."
    out, _ = await run([call("get_kep", {"kep_ref": "583"}, "c1"), answer(text)])
    assert not out["abstained"] and out["answer_markdown"] == "It is provisional [1]. It is stale."


async def test_an_empty_reply_is_asked_once_for_the_text() -> None:
    out, _ = await run([call("get_kep", {"kep_ref": "583"}, "c1"), answer(""), answer(f"It is provisional [[{EID}]].")])
    assert not out["abstained"] and out["answer_markdown"] == "It is provisional [1]."


async def test_ask_budget_forces_the_final_answer() -> None:
    a = agent([call("get_kep", {"kep_ref": "583"}, "c1"), answer(f"It is provisional [[{EID}]].")])
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
    assert not out["abstained"] and seen[0] == ["get_kep"] and seen[1] == []
