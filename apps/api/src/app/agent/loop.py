"""The Q&A agent loop (02 §6): plan → tools → structured final answer → validator.

Live events (status, tool_call, path, citation) are emitted as they happen;
answer text is emitted only after the deterministic validator accepted it
(validate first, then reveal; ADR 0009).
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import ValidationError

from app.agent.cache import AnswerCache
from app.agent.prompts import MEMORY_TOOL, NOT_FOR_PLANNER, SYSTEM_PROMPT, WRITE_NOW, tool_spec
from app.agent.provider import (
    CHARS_PER_TOKEN,
    WAIT_LISTENER,
    Provider,
    ToolCall,
    cost_usd,
    estimate_tokens,
    make_provider,
)
from app.agent.validator import FinalAnswer, Validated, collect_row_urls, link_mentions, parse_answer, validate
from app.db.falkordb import GRAPH_KEP, FalkorPool
from app.db.results import Evidence
from app.errors import AppError
from app.memory import store as memory_store
from app.settings import Settings
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import llm_tools

log = structlog.get_logger(__name__)

MAX_STEPS = 3
MAX_TOOL_CALLS = 8
WALL_BUDGET_S = 90.0
# Token budgets (prompt estimate, 4 chars per token). Groq's free tier allows 8000 tokens per minute per
# model and counts the prompt plus the completion; TURN_TOKEN_BUDGET + MAX_OUTPUT_TOKENS stays under it.
TURN_TOKEN_BUDGET = 5500
ASK_TOKEN_BUDGET = 20000
# What the planner sees of one tool result: at most MAX_ROWS rows, strings cut to TEXT_CHARS, the whole result
# cut to TOOL_RESULT_CHARS; when a turn is over budget every result shrinks to a common cap of at least
# MIN_RESULT_CHARS.
MAX_ROWS = 12
TEXT_CHARS = 280
TOOL_RESULT_CHARS = 4000
MIN_RESULT_CHARS = 200

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


async def _no_emit(event: str, data: dict[str, Any]) -> None:
    return None


class SpendCounter:
    """In-process daily LLM spend (UTC day). One api replica, so memory is enough for v1."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = ""
        self._usd = 0.0

    def _roll(self) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._usd = today, 0.0

    def spent(self) -> float:
        with self._lock:
            self._roll()
            return self._usd

    def add(self, usd: float) -> None:
        with self._lock:
            self._roll()
            self._usd += usd


SPEND = SpendCounter()

KNOWN_ISSUES = """
MATCH (k:KEP) WHERE k.number IN $numbers
MATCH (f:Finding)-[:ABOUT]->(k)
WHERE f.state IN ['open', 'triaged', 'drafted', 'confirmed']
RETURN f.key AS key, f.kind AS kind, k.number AS number, f.a_label AS a_label, f.a_value AS a_value,
 f.b_label AS b_label, f.b_value AS b_value
ORDER BY f.key
LIMIT 10
"""

_KEP_NUM = re.compile(r"\bKEP[-\s#]?(\d{1,5})\b", re.IGNORECASE)


@dataclass
class AskState:
    request_id: str
    question: str
    evidence: dict[str, Evidence] = field(default_factory=dict)
    row_urls: set[str] = field(default_factory=set)
    paths: list[list[str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    prompt_tokens: int = 0  # estimated, for the ask budget


class Agent:
    def __init__(
        self,
        pool: FalkorPool,
        settings: Settings,
        provider: Provider | None = None,
        *,
        turn_token_budget: int = TURN_TOKEN_BUDGET,
        ask_token_budget: int = ASK_TOKEN_BUDGET,
        cache: AnswerCache | None = None,
        use_cache: bool = True,
        wall_budget_s: float = WALL_BUDGET_S,
    ) -> None:
        self.pool = pool
        self.settings = settings
        self._provider = provider
        self.tools = {t.name: t for t in llm_tools()}
        self.turn_token_budget = turn_token_budget
        self.ask_token_budget = ask_token_budget
        self.wall_budget_s = wall_budget_s
        if not use_cache:
            self.cache = None
        else:
            self.cache = cache if cache is not None else (AnswerCache(pool) if pool is not None else None)

    @property
    def provider(self) -> Provider:
        if self._provider is None:
            self._provider = make_provider(self.settings)
        return self._provider

    async def ask(
        self, question: str, request_id: str, memory_id: str | None = None, emit: Emit = _no_emit
    ) -> dict[str, Any]:
        started = time.perf_counter()
        st = AskState(request_id=request_id, question=question)
        await emit("status", {"phase": "understanding", "label": "Reading the question"})
        if self.cache is not None and not memory_id:
            hit = await self.cache.get(question)
            if hit is not None:
                return await self._replay(hit, request_id, started, emit)
        if SPEND.spent() >= self.settings.llm_daily_budget_usd:
            return await self._finish(st, started, emit, None, abstain="budget_exhausted", memory_id=memory_id)

        provider = self.provider
        known, findings_recalled = await self._known_issues(question)
        recalled: list[str] = []
        memory_text = ""
        if memory_id:
            try:
                memory = await memory_store.recall(self.pool, memory_id, question)
                recalled = memory["recalled"]
                memory_text = memory_store.planner_context(memory)
            except AppError:
                recalled = []

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        context = []
        if known:
            context.append(
                "Known issues recorded for KEPs named in the question (context, NOT evidence; verify and cite "
                "through tools):\n" + json.dumps(compact(known), ensure_ascii=False, separators=(",", ":"))
            )
        if memory_text:
            context.append(memory_text)
        if context:
            messages.append({"role": "system", "content": "\n\n".join(context)})
        messages.append({"role": "user", "content": question})

        specs = [
            tool_spec(t)
            for t in self.tools.values()
            if t.name not in NOT_FOR_PLANNER and (memory_id or t.name != MEMORY_TOOL)
        ]
        final: FinalAnswer | None = None
        nudged = False
        await emit("status", {"phase": "querying_graph", "label": "Querying the graph"})

        async def on_wait(wait_s: float) -> None:
            await emit("status", {"phase": "rate_limited", "label": "Waiting for the model's rate limit",
                                  "wait_s": round(wait_s, 1)})  # fmt: skip

        # Scoped to this ask's task: each request runs in its own context.
        listener = WAIT_LISTENER.set(on_wait)
        try:
            for step in range(MAX_STEPS + 1):
                last = step == MAX_STEPS or len(st.tool_calls) >= MAX_TOOL_CALLS
                if time.perf_counter() - started > self.wall_budget_s:
                    last = True
                if not last and st.prompt_tokens + estimate_tokens(messages, specs) > self.ask_token_budget:
                    last = True
                if last:
                    messages.append({"role": "user", "content": WRITE_NOW})
                tools = [] if last else specs
                fit_turn(messages, tools, self.turn_token_budget)
                st.prompt_tokens += estimate_tokens(messages, tools)
                turn = await provider.complete(messages, tools)
                st.input_tokens += turn.input_tokens
                st.output_tokens += turn.output_tokens
                log.info(
                    "llm_turn",
                    request_id=request_id,
                    step=step,
                    tools=len(tools),
                    input_tokens=turn.input_tokens,
                    output_tokens=turn.output_tokens,
                    model=getattr(provider, "last_model", provider.model),
                )
                SPEND.add(
                    cost_usd(getattr(provider, "last_model", provider.model), turn.input_tokens, turn.output_tokens)
                )
                messages.append(turn.raw_message)
                if not turn.tool_calls:
                    if turn.text.strip():
                        final = parse_answer(link_mentions(turn.text, st.evidence))
                        break
                    if last or nudged:
                        break
                    nudged = True
                    messages.append({"role": "user", "content": WRITE_NOW.removeprefix("Tool budget reached. ")})
                    continue
                for call in turn.tool_calls:
                    content = await self._run_tool(st, call, emit)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
        finally:
            WAIT_LISTENER.reset(listener)

        return await self._finish(
            st, started, emit, final, memory_id=memory_id, findings=findings_recalled, recalled=recalled
        )

    async def _replay(self, hit: dict[str, Any], request_id: str, started: float, emit: Emit) -> dict[str, Any]:
        """Serve a cached answer with the events of a live one."""
        for c in hit["citations"]:
            await emit("citation", {"index": c["index"], "evidence_id": c["evidence_id"], "source_type": c["label"],
                                    "title": c["title"], "locator": c["key"], "url": c["url"]})  # fmt: skip
        text = hit["answer_markdown"]
        await emit("status", {"phase": "writing", "label": "Writing the checked answer"})
        for i in range(0, len(text), 40):
            await emit("token", {"text": text[i : i + 40]})
        latency = round((time.perf_counter() - started) * 1000)
        hit.update(request_id=request_id, latency_ms=latency, usage={"input_tokens": 0, "output_tokens": 0})
        await emit("memory", {"recalled": [], "remembered": [], "findings_recalled": hit.get("findings_recalled", [])})
        await emit("done", {"request_id": request_id, "nodes_read": len(hit["graph"]["nodes"]),
                            "sources": len(hit["citations"]), "latency_ms": latency, "abstained": False,
                            "abstain_reason": None, "cached": True, "cached_at": hit["cached_at"]})  # fmt: skip
        return hit

    async def _known_issues(self, question: str) -> tuple[list[dict[str, Any]], list[str]]:
        numbers = sorted({int(n) for n in _KEP_NUM.findall(question)})
        if not numbers:
            return [], []
        try:
            out = await self.pool.ro_query(GRAPH_KEP, KNOWN_ISSUES, {"numbers": numbers})
        except AppError:
            return [], []
        rows = [dict(zip(out.header, r, strict=False)) for r in out.rows]
        return rows, [r["key"] for r in rows]

    async def _run_tool(self, st: AskState, call: ToolCall, emit: Emit) -> str:
        step = len(st.tool_calls) + 1
        record: dict[str, Any] = {"step": step, "name": call.name, "params": call.arguments, "ms": 0.0,
                                  "rows": 0, "truncated": False}  # fmt: skip
        tool = self.tools.get(call.name)
        result: ToolResult | None = None
        new: list[Evidence] = []
        if tool is None:
            record["error"] = "unknown_tool"
            content = json.dumps({"error": f"unknown tool {call.name}"})
        elif len(st.tool_calls) >= MAX_TOOL_CALLS:
            record["error"] = "tool_budget"
            content = json.dumps({"error": "tool budget reached; write the answer"})
        else:
            try:
                ctx = ToolContext(pool=self.pool)
                result = await tool.invoke(ctx, {k: v for k, v in call.arguments.items() if v is not None})
                content = _tool_content(result)
            except ValidationError as exc:
                msgs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
                record["error"] = "invalid_params"
                content = json.dumps({"error": f"invalid parameters: {msgs}"})
            except AppError as exc:
                if exc.code == "graph_unavailable":
                    raise
                record["error"] = exc.code
                content = json.dumps({"error": exc.code})
            except Exception as exc:  # noqa: BLE001 - a failing template must not end the request
                log.warning("tool_failed", tool=call.name, error=str(exc)[:300])
                record["error"] = "tool_failed"
                content = json.dumps({"error": "the tool failed on this input; try different parameters"})
        if result is not None:
            record.update(ms=result.ms, rows=len(result.rows), truncated=result.truncated, template=result.template)
            new = [ev for ev in result.evidence if ev.evidence_id not in st.evidence]
            for ev in result.evidence:
                st.evidence.setdefault(ev.evidence_id, ev)
            collect_row_urls(result.rows, st.row_urls)
            st.paths.extend(result.paths)
        st.tool_calls.append(record)
        await emit("tool_call", record)
        if result is not None:
            if result.paths:
                await emit("path", _graph(result.evidence, result.paths))
            for ev in new:
                await emit("citation", {"evidence_id": ev.evidence_id, "source_type": ev.label, "title": ev.title,
                                        "locator": ev.key, "url": ev.url})  # fmt: skip
        return content

    async def _finish(
        self,
        st: AskState,
        started: float,
        emit: Emit,
        final: FinalAnswer | None,
        *,
        abstain: str | None = None,
        memory_id: str | None = None,
        findings: list[str] | None = None,
        recalled: list[str] | None = None,
    ) -> dict[str, Any]:
        await emit("status", {"phase": "checking", "label": "Checking every claim against the graph"})
        if abstain:
            v = Validated("", [], True, abstain)
        elif final is None:
            v = Validated("", [], True, "unsupported_claims", ["no final answer"])
        elif not st.evidence:
            v = Validated("", [], True, final.abstain_reason or "no_evidence" if final.abstained else "no_evidence")
        else:
            v = validate(final, st.evidence, st.row_urls)
        if v.violations:
            log.info("validator", request_id=st.request_id, abstained=v.abstained, violations=v.violations[:10])
        if v.abstained and v.abstain_reason not in ("no_evidence", "out_of_scope", "unsupported_claims",
                                                     "budget_exhausted", "graph_unavailable"):  # fmt: skip
            v.abstain_reason = "no_evidence"

        remembered: list[str] = []
        if memory_id and not v.abstained:
            try:
                await memory_store.remember(
                    self.pool, memory_id,
                    {"request_id": st.request_id, "question": st.question, "answer_markdown": v.answer_markdown,
                     "abstained": v.abstained, "citations": [c.model_dump() for c in v.citations],
                     "tool_calls": st.tool_calls},
                )  # fmt: skip
                remembered.append(st.request_id)
            except AppError as exc:
                log.warning("remember_failed", error=exc.code)

        for c in v.citations:
            await emit("citation", {"index": c.index, "evidence_id": c.evidence_id, "source_type": c.label,
                                    "title": c.title, "locator": c.key, "url": c.url})  # fmt: skip
        if v.answer_markdown:
            await emit("status", {"phase": "writing", "label": "Writing the checked answer"})
            for i in range(0, len(v.answer_markdown), 40):
                await emit("token", {"text": v.answer_markdown[i : i + 40]})
        latency = round((time.perf_counter() - started) * 1000)
        cited_ids = {c.evidence_id for c in v.citations}
        graph = _graph([e for e in st.evidence.values()], st.paths, prefer=cited_ids)
        response = {
            "request_id": st.request_id,
            "question": st.question,
            "answer_markdown": v.answer_markdown,
            "citations": [c.model_dump() for c in v.citations],
            "tool_calls": [{k: v_ for k, v_ in t.items() if k != "template"} for t in st.tool_calls],
            "graph": graph,
            "abstained": v.abstained,
            "abstain_reason": v.abstain_reason if v.abstained else None,
            "latency_ms": latency,
            "model": getattr(self._provider, "last_model", self.settings.llm_model),
            "findings_recalled": findings or [],
            "memory": {"recalled": recalled or [], "remembered": remembered},
            "usage": {"input_tokens": st.input_tokens, "output_tokens": st.output_tokens},
            "cached": False,
        }
        if self.cache is not None and not memory_id and not v.abstained and v.answer_markdown:
            await self.cache.put(st.question, response)
        await emit("memory", {"recalled": recalled or [], "remembered": remembered,
                              "findings_recalled": findings or []})  # fmt: skip
        await emit("done", {"request_id": st.request_id, "nodes_read": len(st.evidence),
                            "sources": len(v.citations), "latency_ms": latency, "abstained": v.abstained,
                            "abstain_reason": response["abstain_reason"]})  # fmt: skip
        return response


NO_EXACT_MATCH_NOTE = (
    "Nothing with this exact name exists now. Abstain with abstain_reason=no_evidence and name the nearest match "
    "with its citation; a match='historical' feature gate is declared by no current kep.yaml."
)
_DROP_KEYS = frozenset({"url", "source_url", "a_url", "b_url", "metadata_invalid", "is_bot", "kep_path", "sha",
                        "commit_sha", "is_tracking_issue"})  # fmt: skip
# Descriptive fields a shrunk result gives up before it gives up whole rows.
_SLIM_KEYS = frozenset({"title", "label", "creation_date", "created_at_iso", "labels_current", "participating"})


def compact(value: Any) -> Any:
    """The planner's view of tool rows: evidence ids and facts. Drops URLs, nulls, titles that repeat the key or
    summary, keys the node key already carries, and a `path` of node keys next to the `via` edges that spell the
    same hops; long strings are cut to TEXT_CHARS."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in _DROP_KEYS or v is None or v == [] or v == "":
                continue
            if k == "title" and v in (value.get("key"), value.get("summary")):
                continue
            if k == "path" and "via" in value:
                continue
            out[k] = compact(v)
        return out
    if isinstance(value, list):
        return [compact(v) for v in value]
    if isinstance(value, str) and len(value) > TEXT_CHARS:
        return value[:TEXT_CHARS] + "…"
    return value


def dedupe(value: Any, seen: set[str]) -> Any:
    """A node already shown earlier in the payload becomes {evidence_id}."""
    if isinstance(value, dict):
        eid = value.get("evidence_id")
        if isinstance(eid, str) and len(value) > 1:
            if eid in seen:
                return {"evidence_id": eid}
            seen.add(eid)
        return {k: dedupe(v, seen) for k, v in value.items()}
    if isinstance(value, list):
        return [dedupe(v, seen) for v in value]
    return value


def _dump(payload: dict[str, Any]) -> str:
    if "rows" in payload:
        payload = {**payload, "rows": dedupe(payload["rows"], set())}
    return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


def _slim(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _slim(v) for k, v in value.items() if k not in _SLIM_KEYS}
    if isinstance(value, list):
        return [_slim(v) for v in value]
    return value


def _cap_lists(value: Any, n: int) -> Any:
    """Keep the first n items of every nested list; a path is kept whole (its end is the point)."""
    if isinstance(value, dict):
        return {k: v if k == "path" else _cap_lists(v, n) for k, v in value.items()}
    if isinstance(value, list):
        return [_cap_lists(v, n) for v in value[:n]]
    return value


def fit_rows(payload: dict[str, Any], limit: int) -> str:
    """Serialise a tool payload within `limit` characters (never mid-JSON): first drop descriptive fields, then
    cap the lists nested inside rows, and only then drop the last rows."""
    rows = list(payload.get("rows", []))
    omitted = int(payload.get("rows_omitted", 0))
    text = _dump(payload)
    if len(text) <= limit:
        return text
    rows = _slim(rows)
    text = _dump({**payload, "rows": rows, "fields_cut": True})
    for n in (4, 2, 1):
        if len(text) <= limit:
            return text
        rows = [_cap_lists(r, n) for r in rows]
        text = _dump({**payload, "rows": rows, "fields_cut": True, "nested_lists_cut": True})
    while len(text) > limit and rows:
        drop = max(1, len(rows) // 4)
        rows, omitted = rows[:-drop], omitted + drop
        text = _dump({**payload, "rows": rows, "fields_cut": True, "nested_lists_cut": True,
                      "rows_omitted": omitted})  # fmt: skip
    return text


def _tool_content(result: ToolResult) -> str:
    rows = compact(result.rows)
    payload: dict[str, Any] = {"rows": rows[:MAX_ROWS]}
    if result.truncated:
        payload["truncated"] = True
    if len(rows) > MAX_ROWS:
        payload["rows_omitted"] = len(rows) - MAX_ROWS
    if not rows:
        payload["note"] = "no rows"
    elif any(isinstance(r, dict) and "no_exact_match" in r for r in rows):
        payload["note"] = NO_EXACT_MATCH_NOTE
    return fit_rows(payload, TOOL_RESULT_CHARS)


def _shrink_tool_message(message: dict[str, Any], limit: int) -> int:
    """Cut one tool message to `limit` characters; returns the characters saved."""
    before = len(message["content"])
    if before <= limit:
        return 0
    try:
        payload = json.loads(message["content"])
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and "rows" in payload:
        message["content"] = fit_rows(payload, limit)
    if len(message["content"]) > limit:
        message["content"] = _dump({"note": "older result cut; re-run the tool if needed"})
    return before - len(message["content"])


def _even_cap(sizes: list[int], total: int) -> int:
    """The largest per-result cap c with sum(min(size, c)) <= total: small results stay whole, large ones share
    the rest equally."""
    remaining = total
    ordered = sorted(sizes)
    for i, size in enumerate(ordered):
        share = remaining // (len(ordered) - i)
        if size > share:
            return share
        remaining -= size
    return ordered[-1] if ordered else 0


def fit_turn(messages: list[dict[str, Any]], tools: list[dict[str, Any]], budget: int) -> None:
    """Shrink tool results until the request fits the per-turn token budget.

    Every result is cut to one common cap (at least MIN_RESULT_CHARS), so a fact from the first round is not
    thrown away to keep a later, larger result whole; inside a result, descriptive fields go before rows.
    """
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    over = int((estimate_tokens(messages, tools) - budget) * CHARS_PER_TOKEN)
    if over <= 0 or not tool_msgs:
        return
    sizes = [len(m["content"]) for m in tool_msgs]
    cap = max(MIN_RESULT_CHARS, _even_cap(sizes, sum(sizes) - over))
    for m in tool_msgs:
        _shrink_tool_message(m, cap)


def _graph(evidence: list[Evidence], paths: list[list[str]], prefer: set[str] | None = None) -> dict[str, Any]:
    by_key: dict[str, Evidence] = {}
    for ev in evidence:
        by_key.setdefault(ev.key, ev)
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, str]] = {}

    def add(ev: Evidence) -> str:
        nodes.setdefault(ev.evidence_id, {"id": ev.evidence_id, "label": ev.label, "key": ev.key,
                                          "title": ev.title, "url": ev.url})  # fmt: skip
        return ev.evidence_id

    for path in paths:
        for i in range(0, len(path) - 2, 2):
            a, rel, b = by_key.get(path[i]), path[i + 1], by_key.get(path[i + 2])
            if a and b:
                edges.setdefault((add(a), add(b), rel), {"source": a.evidence_id, "target": b.evidence_id,
                                                         "type": rel})  # fmt: skip
    for ev in evidence:
        if prefer and ev.evidence_id in prefer:
            add(ev)
    for ev in evidence:
        if len(nodes) >= 80:
            break
        add(ev)
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}
