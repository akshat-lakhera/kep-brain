"""Per-user memory graph: remember, recall, get, forget (03 §11).

The graph `mem:<ULID>` is created by the first `remember` and by nothing else; every read first checks that
the graph exists, so a lookup never creates one. Facts are taken from the question only. The planner context
built by `recall` carries question, kind, evidence keys and facts, never model-written answer text.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any

import anyio

from app.db.falkordb import FalkorPool, Role
from app.errors import AppError
from app.ingest.common import iso
from app.memory.classify import facts_from_question, kep_numbers, question_kind
from app.settings import get_settings

MEMORY_ID_RE = re.compile(r"[0-9A-Z]{26}")
MAX_EPISODES = 200
RECENT_EPISODES = 5
RELATED_EPISODES = 3
MAX_FACTS = 20
TOP_PROCEDURES = 3
SUMMARY_CHARS = 300

REMEMBER_EPISODE = """
MERGE (u:User {key: $memory_id})
ON CREATE SET u.created_at = $now, u.display_label = $label
SET u.last_active_at = $now
CREATE (e:Episode {key: $request_id, question: $question, question_kind: $kind, answer_summary: $summary,
  abstained: $abstained, evidence_keys: $evidence_keys, tools_used: $tools, created_at: $now,
  created_at_iso: $now_iso, created_ms: $now_ms, observed_at: $now})
CREATE (u)-[:HAS_EPISODE]->(e)
MERGE (p:Procedure {key: $procedure_key})
ON CREATE SET p.question_kind = $kind, p.tool_sequence = $tools, p.success_count = 0, p.failure_count = 0,
  p.description = $description, p.observed_at = $now
SET p.success_count = p.success_count + $ok, p.failure_count = p.failure_count + $failed, p.last_used_at = $now
MERGE (u)-[:HAS_PROCEDURE]->(p)
CREATE (e)-[:USED {outcome: $outcome}]->(p)
"""

REMEMBER_REFS = """
MATCH (e:Episode {key: $request_id})
UNWIND $refs AS ref
MERGE (x:EntityRef {key: ref.key})
ON CREATE SET x.observed_at = $now, x.label = ref.label, x.ref_key = ref.ref_key,
  x.title = ref.title, x.url = ref.url, x.mention_count = 0
SET x.mention_count = x.mention_count + 1, x.last_mentioned_at = $now
MERGE (e)-[:REFERS_TO {role: 'cited'}]->(x)
"""

REMEMBER_FACTS = """
MATCH (u:User {key: $memory_id}), (e:Episode {key: $request_id})
UNWIND $facts AS fa
MERGE (f:Fact {key: fa.key})
ON CREATE SET f.observed_at = $now, f.kind = fa.kind, f.value = fa.value, f.first_seen_at = $now, f.support_count = 0,
  f.extractor = 'question_rules'
SET f.support_count = f.support_count + 1, f.last_seen_at = $now,
  f.confidence = CASE WHEN 0.6 + 0.1 * f.support_count > 0.95 THEN 0.95 ELSE 0.6 + 0.1 * f.support_count END
MERGE (u)-[:HAS_FACT]->(f)
MERGE (f)-[:LEARNED_FROM {at: $now}]->(e)
"""

COMPACT = """
MATCH (e:Episode)
WITH e ORDER BY e.created_ms DESC, e.key SKIP $max
DETACH DELETE e
"""
COMPACT_ORPHANS = "MATCH (x:EntityRef) WHERE NOT ()-[:REFERS_TO]->(x) DETACH DELETE x"
EPISODE_EXISTS = "MATCH (e:Episode {key: $request_id}) RETURN count(e) AS n"
EPISODE_COUNT = "MATCH (e:Episode) RETURN count(e) AS n"
COUNTS = "MATCH (n) WITH count(n) AS nodes OPTIONAL MATCH ()-[r]->() RETURN nodes, count(r) AS edges"

EPISODES = """
MATCH (e:Episode)
RETURN e.key AS request_id, e.question AS question, e.question_kind AS question_kind,
 e.answer_summary AS answer_summary, e.abstained AS abstained, e.evidence_keys AS evidence_keys,
 e.created_at_iso AS created_at
ORDER BY e.created_ms DESC, e.key
LIMIT $limit
"""
FACTS = """
MATCH (f:Fact)
RETURN f.key AS key, f.kind AS kind, f.value AS value, f.confidence AS confidence,
 f.support_count AS support_count, f.last_seen_at AS last_seen_at
ORDER BY f.confidence * f.support_count DESC, f.key
LIMIT $limit
"""
PROCEDURES = """
MATCH (p:Procedure)
WHERE $kind IS NULL OR p.question_kind = $kind
RETURN p.key AS key, p.question_kind AS question_kind, p.tool_sequence AS tool_sequence,
 p.success_count AS success_count, p.failure_count AS failure_count, p.description AS description,
 p.last_used_at AS last_used_at, p.observed_at AS observed_at
ORDER BY p.success_count DESC, p.last_used_at DESC, p.key
LIMIT $limit
"""
DELETE_PROCEDURE = "MATCH (p:Procedure {key: $key}) DETACH DELETE p RETURN 1"
DELETE_FACT = "MATCH (f:Fact {key: $key}) DETACH DELETE f RETURN 1"


def valid_memory_id(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().upper()
    return candidate if MEMORY_ID_RE.fullmatch(candidate) else None


def memory_graph_name(memory_id: str) -> str:
    """The only place a graph name is built; graph names cannot be query parameters."""
    if not MEMORY_ID_RE.fullmatch(memory_id):
        raise AppError("bad_request", {"reason": "memory id must be a 26 character ULID"})
    return f"mem:{memory_id}"


def _rows(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(header, row, strict=False)) for row in rows]


# Graphs known to exist, with the time that knowledge expires. A graph never stops existing on its own, so a
# positive answer can be reused for a while; a negative one is re-checked every time (a GRAPH.LIST round trip).
_KNOWN: dict[str, float] = {}
_KNOWN_TTL_S = 30.0


async def _exists(pool: FalkorPool, memory_id: str) -> bool:
    now = time.monotonic()
    if _KNOWN.get(memory_id, 0.0) > now:
        return True
    found = memory_graph_name(memory_id) in await pool.ping()
    if found:
        _KNOWN[memory_id] = now + _KNOWN_TTL_S
    return found


async def _ensure_capacity(pool: FalkorPool) -> None:
    """A new memory graph is refused once MEMORY_MAX_GRAPHS exist; existing memories keep working."""
    cap = get_settings().memory_max_graphs
    if sum(1 for name in await pool.ping() if name.startswith("mem:")) >= cap:
        raise AppError("rate_limited", {"reason": "memory capacity reached; try again later", "scope": "memory_graphs"})


async def _read(pool: FalkorPool, memory_id: str, query: str, params: dict[str, Any] | None = None) -> list[Any]:
    out = await pool.ro_query(memory_graph_name(memory_id), query, params or {})
    return _rows(out.header, out.rows)


async def _write(pool: FalkorPool, memory_id: str, query: str, params: dict[str, Any]) -> list[list[Any]]:
    return (await pool.write(Role.MEMORY, memory_graph_name(memory_id), query, params)).rows


def _summary(answer_markdown: str) -> str:
    text = re.sub(r"\[\d+\]", "", answer_markdown)
    return re.sub(r"\s+", " ", text).strip()[:SUMMARY_CHARS]


def _evidence_keys(citations: Sequence[Mapping[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for c in citations:
        if c.get("label") and c.get("key"):
            seen[f"{c['label']}|{c['key']}"] = None
    return list(seen)[:50]


async def remember(pool: FalkorPool, memory_id: str, ask_result: Mapping[str, Any]) -> bool:
    """Store one answered question. Returns False when the request was already remembered."""
    request_id = str(ask_result["request_id"])
    question = str(ask_result["question"])
    if await _exists(pool, memory_id):
        if (await _read(pool, memory_id, EPISODE_EXISTS, {"request_id": request_id}))[0]["n"]:
            return False
    else:
        await _ensure_capacity(pool)

    now = time.time()
    kind = question_kind(question)
    tools = [str(t["name"]) for t in ask_result.get("tool_calls", []) if t.get("name")][:20]
    citations: Sequence[Mapping[str, Any]] = ask_result.get("citations", [])
    abstained = bool(ask_result.get("abstained"))
    base: dict[str, Any] = {"memory_id": memory_id, "request_id": request_id, "now": int(now)}
    await _write(
        pool,
        memory_id,
        REMEMBER_EPISODE,
        base
        | {
            "label": memory_id[:6],
            "question": question[:1000],
            "kind": kind,
            "summary": "" if abstained else _summary(str(ask_result.get("answer_markdown", ""))),
            "abstained": abstained,
            "evidence_keys": _evidence_keys(citations),
            "tools": tools,
            "now_iso": iso(int(now)),
            "now_ms": int(now * 1000),
            "procedure_key": f"{kind}:{hashlib.sha1('|'.join(tools).encode()).hexdigest()[:12]}",
            "description": f"For {kind} questions: " + (" -> ".join(tools) if tools else "answer without tools"),
            "ok": 0 if abstained else 1,
            "failed": 1 if abstained else 0,
            "outcome": "abstained" if abstained else "answered",
        },
    )
    refs = [
        {
            "key": f"{c['label']}|{c['key']}",
            "label": c["label"],
            "ref_key": c["key"],
            "title": c.get("title", ""),
            "url": c.get("url", ""),
        }
        for c in citations[:50]
        if c.get("label") and c.get("key")
    ]
    if refs:
        await _write(pool, memory_id, REMEMBER_REFS, base | {"refs": refs})
    facts = facts_from_question(question)
    if facts:
        rows = [{"key": f.key, "kind": f.kind, "value": f.value} for f in facts]
        await _write(pool, memory_id, REMEMBER_FACTS, base | {"facts": rows})
    await compact(pool, memory_id)
    return True


async def compact(pool: FalkorPool, memory_id: str, max_episodes: int = MAX_EPISODES) -> int:
    """Drop the oldest episodes beyond the quota. Facts and procedures already hold their aggregate."""
    count = (await _read(pool, memory_id, EPISODE_COUNT))[0]["n"]
    if count <= max_episodes:
        return 0
    await _write(pool, memory_id, COMPACT, {"max": max_episodes})
    await _write(pool, memory_id, COMPACT_ORPHANS, {})
    return int(count - max_episodes)


async def recall(pool: FalkorPool, memory_id: str, question: str) -> dict[str, Any]:
    """Planner context for a question: recent and related episodes, top facts, procedures for the question kind.

    Episodes carry question, kind and evidence keys only; answer text is never returned here.
    """
    kind = question_kind(question)
    result: dict[str, Any] = {
        "memory_id": memory_id,
        "question_kind": kind,
        "episodes": [],
        "facts": [],
        "procedures": [],
        "recalled": [],
    }
    if not await _exists(pool, memory_id):
        return result
    episodes = await _read(pool, memory_id, EPISODES, {"limit": MAX_EPISODES})
    wanted = kep_numbers(question)
    related = [
        e for e in episodes[RECENT_EPISODES:] if wanted and any(n in kep_numbers(e["question"]) for n in wanted)
    ][:RELATED_EPISODES]
    chosen = [
        {k: e[k] for k in ("request_id", "question", "question_kind", "evidence_keys", "created_at")}
        for e in [*episodes[:RECENT_EPISODES], *related]
    ]
    facts = await _read(pool, memory_id, FACTS, {"limit": MAX_FACTS})
    procedures = rank_playbooks(await _read(pool, memory_id, PROCEDURES, {"kind": kind, "limit": 20}))
    result.update(
        episodes=chosen,
        facts=facts,
        procedures=procedures,
        recalled=[e["request_id"] for e in chosen] + [f["key"] for f in facts] + [p["key"] for p in procedures],
    )
    return result


def rank_playbooks(rows: Sequence[Mapping[str, Any]], limit: int = TOP_PROCEDURES) -> list[dict[str, Any]]:
    """Playbooks that worked at least once and used tools, best success rate first, then most successes, then recent."""
    usable = [dict(r) for r in rows if (r.get("success_count") or 0) > 0 and r.get("tool_sequence")]

    def score(r: Mapping[str, Any]) -> tuple[float, int, int]:
        ok, bad = int(r["success_count"]), int(r.get("failure_count") or 0)
        return ok / (ok + bad), ok, int(r.get("last_used_at") or 0)

    return sorted(usable, key=score, reverse=True)[:limit]


def planner_context(recalled: Mapping[str, Any]) -> str:
    """Text block for the planner prompt. Memory is context, not evidence."""
    lines: list[str] = []
    for e in recalled.get("episodes", []):
        keys = ", ".join(e["evidence_keys"][:5])
        suffix = f" [evidence: {keys}]" if keys else ""
        lines.append(f"- earlier question ({e['question_kind']}): {e['question']}{suffix}")
    lines.extend(f"- user fact {f['key']}: {f['value']}" for f in recalled.get("facts", []))
    lines.extend(
        f"- tool sequence that worked for {p['question_kind']} questions "
        f"({p['success_count']}x): {' -> '.join(p['tool_sequence'])}"
        for p in recalled.get("procedures", [])
        if p.get("tool_sequence")
    )
    if not lines:
        return ""
    return "Memory about this user (context, NOT evidence; cite only graph evidence):\n" + "\n".join(lines)


async def get_memory(pool: FalkorPool, memory_id: str) -> dict[str, Any]:
    """The Memory page view: the user's own episodes (with their summaries), facts and procedures."""
    if not await _exists(pool, memory_id):
        return {
            "memory_id": memory_id,
            "exists": False,
            "recent_episodes": [],
            "procedures": [],
            "playbooks": [],
            "facts": [],
            "episode_count": 0,
            "quota": MAX_EPISODES,
            "graph": {"nodes": 0, "edges": 0},
        }
    counts = (await _read(pool, memory_id, COUNTS))[0]
    procedures = await _read(pool, memory_id, PROCEDURES, {"kind": None, "limit": 20})
    return {
        "memory_id": memory_id,
        "exists": True,
        "recent_episodes": await _read(pool, memory_id, EPISODES, {"limit": 50}),
        "procedures": procedures,
        "playbooks": procedures,
        "facts": await _read(pool, memory_id, FACTS, {"limit": 50}),
        "episode_count": (await _read(pool, memory_id, EPISODE_COUNT))[0]["n"],
        "quota": MAX_EPISODES,
        "graph": {"nodes": counts["nodes"], "edges": counts["edges"]},
    }


async def forget(pool: FalkorPool, memory_id: str) -> bool:
    """Delete the whole graph. False when there was nothing to delete."""
    if not await _exists(pool, memory_id):
        return False
    graph = pool.graph(Role.MEMORY, memory_graph_name(memory_id))
    await anyio.to_thread.run_sync(graph.delete)
    _KNOWN.pop(memory_id, None)
    return True


async def forget_fact(pool: FalkorPool, memory_id: str, key: str) -> bool:
    if not await _exists(pool, memory_id):
        return False
    return bool(await _write(pool, memory_id, DELETE_FACT, {"key": key}))


async def forget_playbook(pool: FalkorPool, memory_id: str, key: str) -> bool:
    if not await _exists(pool, memory_id):
        return False
    return bool(await _write(pool, memory_id, DELETE_PROCEDURE, {"key": key}))
