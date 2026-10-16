"""Coordination in the `ops` graph: tasks, leases, handoffs, drafts (03 §10, §10.1, ADR 0012).

`ops` is coordination state, not agent memory. Roles: `freshness` (LLM triage), `action` (deterministic draft of a
stale-doc issue, never posted) and `verifier` (checks the draft cites only the finding's evidence). Every lease
comparison uses `timestamp()` on the FalkorDB server. Each claim, complete, handoff and fail is one fenced query.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from openai import OpenAIError
from ulid import ULID

from app.db.falkordb import GRAPH_KEP, GRAPH_OPS, FalkorPool, Role
from app.errors import AppError
from app.settings import Settings
from app.worker.freshness import (
    CITATION,
    URL,
    FindingContext,
    Llm,
    OpenAICompatibleLlm,
    budget_left,
    gather_context,
    triage_finding,
)

log = structlog.get_logger(__name__)

LEASE_MS = 300_000
MAX_ATTEMPTS = 3
RETRY_COOLDOWN_S = 24 * 3600  # a done or failed task blocks a new one for the same finding this long
MAX_PER_ROLE_PER_TICK = 25
STATE_JSON_MAX = 8192
AGENTS: dict[str, str] = {"freshness": "llm_agent", "action": "worker_role", "verifier": "worker_role"}
FIX_TEXT = {
    "set_status_implemented": "Set the KEP status to `implemented` in kep.yaml.",
    "set_status_withdrawn_or_deferred": "Set the KEP status to `withdrawn` or `deferred` in kep.yaml.",
    "add_superseded_by": "Add the missing `superseded-by` entry to the predecessor's kep.yaml.",
    "update_latest_milestone": "Update `latest-milestone` in kep.yaml to match the tracking issue.",
    "update_stage": "Update `stage` in kep.yaml to match the tracking issue.",
    "remove_future_milestones": "Remove the future milestones from kep.yaml.",
    "other": "A maintainer should reconcile the two records.",
}

CLAIM = """
MATCH (t:Task {role: $role})
WHERE t.attempts < $max_attempts AND (t.status = 'queued' OR (t.status = 'running' AND t.lease_until_ms < timestamp()))
WITH t ORDER BY t.key LIMIT 1
SET t.status = 'running', t.claimed_by = $agent, t.attempts = t.attempts + 1,
 t.lease_until_ms = timestamp() + $lease_ms, t.heartbeat_at_ms = timestamp(),
 t.updated_at = $now, t.updated_at_iso = $iso
WITH t
MERGE (a:Agent {key: $agent})
ON CREATE SET a.kind = $agent_kind
SET a.status = 'working', a.current_task = t.key, a.last_seen_at = $now, a.last_seen_at_iso = $iso
CREATE (a)-[:CLAIMED {at_ms: timestamp(), lease_until_ms: t.lease_until_ms, attempt: t.attempts}]->(t)
RETURN t.key AS key, t.kind AS kind, t.finding_key AS finding_key, t.payload_json AS payload_json,
 t.attempts AS attempt
"""
HEARTBEAT = """
MATCH (t:Task {key: $key, status: 'running', claimed_by: $agent, attempts: $attempt})
SET t.lease_until_ms = timestamp() + $lease_ms, t.heartbeat_at_ms = timestamp()
RETURN t.key
"""
FINISH = """
MATCH (t:Task {key: $key, status: 'running', claimed_by: $agent, attempts: $attempt})
SET t.status = $status, t.finished_at = $now, t.result_json = $result, t.error = $error,
 t.updated_at = $now, t.updated_at_iso = $iso
REMOVE t.lease_until_ms, t.claimed_by, t.heartbeat_at_ms
WITH t
MATCH (a:Agent {key: $agent})
SET a.status = 'idle', a.current_task = '', a.last_seen_at = $now, a.last_seen_at_iso = $iso
RETURN t.key
"""
PRODUCED = "MATCH (t:Task {key: $task}), (d:ActionDraft {key: $draft}) MERGE (t)-[:PRODUCED]->(d)"
HANDOFF = """
MATCH (t:Task {key: $key, status: 'running', claimed_by: $agent, attempts: $attempt})
SET t.role = $to_role, t.kind = $to_kind, t.status = 'queued', t.attempts = 0,
 t.updated_at = $now, t.updated_at_iso = $iso
REMOVE t.lease_until_ms, t.claimed_by, t.heartbeat_at_ms
WITH t
MERGE (src:Agent {key: $from_role})
ON CREATE SET src.kind = $from_kind
SET src.status = 'idle', src.current_task = '', src.last_seen_at = $now, src.last_seen_at_iso = $iso
MERGE (dst:Agent {key: $to_role})
ON CREATE SET dst.kind = $to_kind_agent
CREATE (h:Handoff {key: $handoff, at: $now, at_iso: $iso, reason: $reason, from_role: $from_role,
 to_role: $to_role, finding_key: $finding_key, state_json: $state_json})
CREATE (t)-[:HAS_HANDOFF]->(h), (h)-[:FROM_AGENT]->(src), (h)-[:TO_AGENT]->(dst)
RETURN h.key
"""
REAP = """
MATCH (t:Task)
WHERE t.status = 'running' AND t.lease_until_ms < timestamp() AND t.attempts >= $max_attempts
SET t.status = 'failed', t.error = 'lease_expired', t.updated_at = $now, t.updated_at_iso = $iso
REMOVE t.lease_until_ms, t.claimed_by
RETURN count(t)
"""
ENQUEUE = """
OPTIONAL MATCH (e:Task {kind: $kind, finding_key: $finding_key})
WHERE e.status IN ['queued', 'running'] OR e.updated_at > $retry_after
WITH count(e) AS existing WHERE existing = 0
CREATE (t:Task {key: $key, kind: $kind, role: $role, status: 'queued', finding_key: $finding_key,
 payload_json: $payload, created_at: $now, created_at_iso: $iso, updated_at: $now, updated_at_iso: $iso,
 attempts: 0})
RETURN t.key
"""
UPSERT_AGENT = """
MERGE (a:Agent {key: $key})
ON CREATE SET a.kind = $kind, a.status = 'idle', a.current_task = ''
SET a.model = $model, a.last_seen_at = $now, a.last_seen_at_iso = $iso, a.host = $host, a.version = $version
"""
FIND_DRAFT = "MATCH (d:ActionDraft {finding_key: $finding_key}) RETURN d.key ORDER BY d.key LIMIT 1"
CREATE_DRAFT = """
CREATE (d:ActionDraft {key: $key, kind: 'stale_doc_issue', kep_path: $kep_path, finding_key: $finding_key,
 title: $title, body: $body, evidence_keys: $evidence_keys, status: 'drafted', created_by: 'worker',
 created_at: $now, created_at_iso: $iso})
RETURN d.key
"""
READ_DRAFT = "MATCH (d:ActionDraft {key: $key}) RETURN d.title, d.body, d.evidence_keys, d.status"
SET_DRAFT_STATUS = "MATCH (d:ActionDraft {key: $key}) SET d.status = $status, d.verified_at = $now RETURN d.key"
FINDING_TO_DRAFTED = """
MATCH (f:Finding {key: $key})
WHERE f.state = 'triaged'
SET f.state = 'drafted', f.action_draft_key = $draft
RETURN f.key
"""
FINDING_DRAFT_KEY = "MATCH (f:Finding {key: $key}) RETURN f.action_draft_key"
OPEN_FINDINGS = "MATCH (f:Finding {state: 'open'}) RETURN f.key ORDER BY f.key"
CONFIRMED_UNDRAFTED = """
MATCH (f:Finding {state: 'triaged', triage_verdict: 'confirmed'})
WHERE f.action_draft_key IS NULL
RETURN f.key ORDER BY f.key
"""

BOARD_AGENTS = """
MATCH (a:Agent)
RETURN a.key AS name, a.kind AS kind, a.model AS model, a.status AS status, a.current_task AS current_task,
 a.last_seen_at_iso AS last_seen_at
ORDER BY a.key
LIMIT 50
"""
BOARD_TASKS = """
MATCH (t:Task)
RETURN t.key AS key, t.kind AS kind, t.role AS role, t.status AS status, t.finding_key AS finding_key,
 t.claimed_by AS claimed_by, t.attempts AS attempts, t.updated_at_iso AS updated_at
ORDER BY t.updated_at DESC, t.key
LIMIT 50
"""
BOARD_HANDOFFS = """
MATCH (h:Handoff)
WHERE h.at >= $since
RETURN h.key AS key, h.from_role AS from_role, h.to_role AS to_role, h.finding_key AS finding_key,
 h.at_iso AS at, h.reason AS reason
ORDER BY h.at DESC, h.key
LIMIT 50
"""
BOARD_DRAFTS = """
MATCH (d:ActionDraft)
RETURN d.key AS key, d.finding_key AS finding_key, d.kep_path AS kep_path, d.title AS title, d.status AS status
ORDER BY d.created_at DESC, d.key
LIMIT 20
"""
BOARD_FINDINGS = """
MATCH (f:Finding)
RETURN f.key AS key, f.kind AS kind, f.kep_path AS kep_path, f.state AS state, f.detected_at_iso AS detected_at_iso,
 f.triage_verdict AS triage_verdict
ORDER BY f.detected_at DESC, f.key
LIMIT 20
"""


@dataclass(frozen=True)
class ClaimedTask:
    key: str
    kind: str
    role: str
    finding_key: str | None
    payload: dict[str, Any]
    attempt: int


def _stamp() -> dict[str, Any]:
    now = int(time.time())
    return {"now": now, "iso": datetime.fromtimestamp(now, UTC).isoformat()}


def _run(pool: FalkorPool, graph: str, query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    return pool.run_sync(Role.WRITER, graph, query, params or {}, read_only=False, timeout_ms=10000).rows


def ensure_agents(pool: FalkorPool, settings: Settings, graph: str = GRAPH_OPS) -> None:
    for role, kind in AGENTS.items():
        _run(
            pool,
            graph,
            UPSERT_AGENT,
            {
                "key": role,
                "kind": kind,
                "model": settings.llm_model_cheap if role == "freshness" else None,
                "host": socket.gethostname(),
                "version": os.environ.get("GIT_SHA", "dev"),
                **_stamp(),
            },
        )


def enqueue_task(
    pool: FalkorPool,
    kind: str,
    role: str,
    finding_key: str,
    payload: dict[str, Any] | None = None,
    graph: str = GRAPH_OPS,
) -> str | None:
    """Create a queued task unless one of this kind is queued or running for the finding, or finished recently.

    A finished (done or failed) task blocks a new one only for RETRY_COOLDOWN_S, so a rejected triage or a
    finding reopened later is tried again, but not on every tick.
    """
    key = str(ULID())
    stamp = _stamp()
    rows = _run(
        pool,
        graph,
        ENQUEUE,
        {"key": key, "kind": kind, "role": role, "finding_key": finding_key,
         "payload": json.dumps(payload or {}), "retry_after": stamp["now"] - RETRY_COOLDOWN_S, **stamp},
    )  # fmt: skip
    return key if rows else None


def claim(pool: FalkorPool, role: str, graph: str = GRAPH_OPS) -> ClaimedTask | None:
    """Atomically claim the oldest eligible task of `role` with a 5 minute lease."""
    rows = _run(
        pool,
        graph,
        CLAIM,
        {"role": role, "agent": role, "agent_kind": AGENTS[role], "max_attempts": MAX_ATTEMPTS,
         "lease_ms": LEASE_MS, **_stamp()},
    )  # fmt: skip
    if not rows:
        return None
    key, kind, finding_key, payload, attempt = rows[0]
    return ClaimedTask(key, kind, role, finding_key, json.loads(payload or "{}"), attempt)


def heartbeat(pool: FalkorPool, task: ClaimedTask, graph: str = GRAPH_OPS) -> bool:
    """False means the lease was lost and the work must be discarded."""
    rows = _run(
        pool, graph, HEARTBEAT,
        {"key": task.key, "agent": task.role, "attempt": task.attempt, "lease_ms": LEASE_MS},
    )  # fmt: skip
    return bool(rows)


def _finish(
    pool: FalkorPool, task: ClaimedTask, status: str, result: dict[str, Any] | None, error: str | None, graph: str
) -> bool:
    rows = _run(
        pool,
        graph,
        FINISH,
        {"key": task.key, "agent": task.role, "attempt": task.attempt, "status": status,
         "result": json.dumps(result) if result is not None else None, "error": error, **_stamp()},
    )  # fmt: skip
    return bool(rows)


def complete(
    pool: FalkorPool,
    task: ClaimedTask,
    result: dict[str, Any],
    produced_draft: str | None = None,
    graph: str = GRAPH_OPS,
) -> bool:
    done = _finish(pool, task, "done", result, None, graph)
    if done and produced_draft:
        _run(pool, graph, PRODUCED, {"task": task.key, "draft": produced_draft})
    return done


def fail(pool: FalkorPool, task: ClaimedTask, error: str, graph: str = GRAPH_OPS) -> bool:
    return _finish(pool, task, "failed", None, error[:500], graph)


def handoff(
    pool: FalkorPool,
    task: ClaimedTask,
    to_role: str,
    to_kind: str,
    reason: str,
    state: dict[str, Any],
    graph: str = GRAPH_OPS,
) -> str | None:
    """Pass a running task to another role, leaving a `Handoff`. None means the lease was lost."""
    state_json = json.dumps(state, ensure_ascii=False)
    if len(state_json.encode()) > STATE_JSON_MAX:
        raise ValueError("handoff state exceeds 8 KB")
    key = str(ULID())
    rows = _run(
        pool,
        graph,
        HANDOFF,
        {"key": task.key, "agent": task.role, "attempt": task.attempt, "to_role": to_role, "to_kind": to_kind,
         "from_role": task.role, "from_kind": AGENTS[task.role], "to_kind_agent": AGENTS[to_role],
         "handoff": key, "reason": reason, "finding_key": task.finding_key, "state_json": state_json,
         **_stamp()},
    )  # fmt: skip
    return key if rows else None


def reap(pool: FalkorPool, graph: str = GRAPH_OPS) -> int:
    rows = _run(pool, graph, REAP, {"max_attempts": MAX_ATTEMPTS, **_stamp()})
    return int(rows[0][0]) if rows else 0


# -- deterministic draft and its check ----------------------------------------------------------------------------


def _cited_links(text: str, ctx: FindingContext) -> str:
    by_id = {r.evidence_id: r for r in ctx.rows}
    order: dict[str, int] = {}

    def link(m: re.Match[str]) -> str:
        eid = m.group(1)
        row = by_id.get(eid)
        if row is None:
            return ""
        n = order.setdefault(eid, len(order) + 1)
        return f"[{n}]({row.url})"

    return CITATION.sub(link, text)


def compose_draft(ctx: FindingContext) -> tuple[str, str]:
    """Title and Markdown body built only from the finding's sides, its triage and its evidence rows."""
    kep = next((r for r in ctx.rows if r.label == "KEP"), None)
    number = kep.props.get("number") if kep else None
    name = f"KEP-{number}" if number is not None else (kep.key if kep else ctx.key)
    title = f"Stale metadata in {name}: {ctx.sides['a_label']} vs {ctx.sides['b_label']}"
    lines = [
        f"{name} has two public records that disagree.",
        "",
        "## Records",
        f"- {ctx.sides['a_label']}: {ctx.sides['a_value']} ({ctx.sides['a_url']})",
        f"- {ctx.sides['b_label']}: {ctx.sides['b_value']} ({ctx.sides['b_url']})",
        "",
        "## Suggested fix",
        FIX_TEXT.get(ctx.suggested_fix, FIX_TEXT["other"]),
    ]
    if ctx.assessment:
        lines += ["", "## Automated triage (advisory, not reviewed by a maintainer)", _cited_links(ctx.assessment, ctx)]
    lines += ["", "## Evidence"]
    lines += [f"- {r.label} `{r.key}`: {r.url}" for r in ctx.rows if r.url]
    return title, "\n".join(lines)


def check_draft(ctx: FindingContext, title: str, body: str, evidence_keys: list[str]) -> list[str]:
    """Problems that stop a draft from being verified. Empty means every link and key is the finding's evidence."""
    allowed_urls = {ctx.sides["a_url"], ctx.sides["b_url"], *(r.url for r in ctx.rows)}
    problems = [
        f"url not in evidence: {u}" for u in dict.fromkeys(URL.findall(body)) if u.rstrip(".,;)") not in allowed_urls
    ]
    problems += [f"missing source link: {ctx.sides[k]}" for k in ("a_url", "b_url") if ctx.sides[k] not in body]
    known = {f"{r.label}|{r.key}" for r in ctx.rows}
    problems += [f"evidence key not given: {k}" for k in evidence_keys if k not in known]
    if not title.strip():
        problems.append("empty title")
    return problems


# -- role executors -------------------------------------------------------------------------------------------


def _run_triage(
    pool: FalkorPool, settings: Settings, task: ClaimedTask, llm: Llm, kep_graph: str, ops_graph: str
) -> str:
    assert task.finding_key is not None
    try:
        result = triage_finding(pool, settings, task.finding_key, llm, kep_graph=kep_graph, ops_graph=ops_graph)
    except (OpenAIError, AppError) as exc:
        fail(pool, task, f"llm_error: {type(exc).__name__}", ops_graph)
        return "failed"
    if result["status"] == "rejected":
        fail(pool, task, f"triage_rejected: {result['reason']}", ops_graph)
        return "failed"
    if result["status"] == "triaged" and result["verdict"] == "confirmed":
        state = {"verdict": result["verdict"], "confidence": result["confidence"], "assessment": result["assessment"]}
        if handoff(pool, task, "action", "draft_stale_issue", "triage_confirmed", state, ops_graph):
            return "handed_off"
        return "lease_lost"
    complete(pool, task, {k: v for k, v in result.items() if k != "assessment"}, graph=ops_graph)
    return "done"


def _run_draft(pool: FalkorPool, task: ClaimedTask, kep_graph: str, ops_graph: str) -> str:
    assert task.finding_key is not None
    ctx = gather_context(pool, task.finding_key, kep_graph)
    if ctx is None or ctx.state not in ("triaged", "drafted"):
        fail(pool, task, "finding is not triaged", ops_graph)
        return "failed"
    existing = _run(pool, ops_graph, FIND_DRAFT, {"finding_key": task.finding_key})
    if existing:
        draft_key = existing[0][0]
    else:
        title, body = compose_draft(ctx)
        draft_key = str(ULID())
        _run(
            pool,
            ops_graph,
            CREATE_DRAFT,
            {"key": draft_key, "kep_path": _kep_path(ctx), "finding_key": ctx.key, "title": title, "body": body,
             "evidence_keys": [f"{r.label}|{r.key}" for r in ctx.rows], **_stamp()},
        )  # fmt: skip
    _run(pool, kep_graph, FINDING_TO_DRAFTED, {"key": ctx.key, "draft": draft_key})
    if handoff(pool, task, "verifier", "verify_draft", "draft_created", {"draft": draft_key}, ops_graph):
        return "handed_off"
    return "lease_lost"


def _kep_path(ctx: FindingContext) -> str:
    kep = next((r for r in ctx.rows if r.label == "KEP"), None)
    return kep.key if kep else ""


def _run_verify(pool: FalkorPool, task: ClaimedTask, kep_graph: str, ops_graph: str) -> str:
    assert task.finding_key is not None
    ctx = gather_context(pool, task.finding_key, kep_graph)
    draft_key = _run(pool, kep_graph, FINDING_DRAFT_KEY, {"key": task.finding_key})
    draft = _run(pool, ops_graph, READ_DRAFT, {"key": draft_key[0][0]}) if draft_key and draft_key[0][0] else []
    if ctx is None or not draft:
        fail(pool, task, "no draft to verify", ops_graph)
        return "failed"
    title, body, evidence_keys, _ = draft[0]
    problems = check_draft(ctx, title, body, evidence_keys)
    stamp = _stamp()
    if problems:
        _run(pool, ops_graph, SET_DRAFT_STATUS, {"key": draft_key[0][0], "status": "failed", "now": stamp["now"]})
        fail(pool, task, "draft_rejected: " + "; ".join(problems)[:400], ops_graph)
        return "failed"
    _run(pool, ops_graph, SET_DRAFT_STATUS, {"key": draft_key[0][0], "status": "verified", "now": stamp["now"]})
    complete(
        pool, task, {"draft": draft_key[0][0], "status": "verified"}, produced_draft=draft_key[0][0], graph=ops_graph
    )
    return "done"


def _enqueue_pending(pool: FalkorPool, kep_graph: str, ops_graph: str) -> dict[str, int]:
    created = {"triage_finding": 0, "draft_stale_issue": 0}
    for (key,) in pool.run_sync(Role.WRITER, kep_graph, OPEN_FINDINGS, read_only=True, timeout_ms=10000).rows:
        created["triage_finding"] += enqueue_task(pool, "triage_finding", "freshness", key, graph=ops_graph) is not None
    for (key,) in pool.run_sync(Role.WRITER, kep_graph, CONFIRMED_UNDRAFTED, read_only=True, timeout_ms=10000).rows:
        created["draft_stale_issue"] += (
            enqueue_task(pool, "draft_stale_issue", "action", key, graph=ops_graph) is not None
        )
    return created


def run_coordination_tick(
    settings: Settings,
    *,
    llm: Llm | None = None,
    pool: FalkorPool | None = None,
    kep_graph: str = GRAPH_KEP,
    ops_graph: str = GRAPH_OPS,
    max_per_role: int = MAX_PER_ROLE_PER_TICK,
) -> dict[str, Any]:
    """One scheduler tick: reap, enqueue, then let freshness, action and verifier drain what they can claim."""
    own_pool = pool is None
    pool = pool or FalkorPool(settings)
    try:
        ensure_agents(pool, settings, ops_graph)
        summary: dict[str, Any] = {"reaped": reap(pool, ops_graph), "enqueued": {}, "processed": {}}
        if settings.findings_agent_enabled:
            summary["enqueued"] = _enqueue_pending(pool, kep_graph, ops_graph)
        else:
            summary["enqueued"] = {"triage_finding": 0, "draft_stale_issue": 0}
        for role in ("freshness", "action", "verifier"):
            outcomes: dict[str, int] = {}
            agent = llm if role == "freshness" else None
            if role == "freshness":
                if not settings.findings_agent_enabled:
                    continue
                if agent is None:
                    try:
                        agent = OpenAICompatibleLlm(settings)
                    except AppError:
                        log.warning("freshness_skipped", reason="no llm key")
                        continue
            for _ in range(max_per_role):
                if role == "freshness" and not budget_left(pool, settings, ops_graph):
                    summary["stopped"] = "daily_cap_reached"
                    break
                task = claim(pool, role, ops_graph)
                if task is None:
                    break
                if role == "freshness":
                    assert agent is not None
                    outcome = _run_triage(pool, settings, task, agent, kep_graph, ops_graph)
                elif role == "action":
                    outcome = _run_draft(pool, task, kep_graph, ops_graph)
                else:
                    outcome = _run_verify(pool, task, kep_graph, ops_graph)
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
            summary["processed"][role] = outcomes
        log.info("coordination_tick", **summary)
        return summary
    finally:
        if own_pool:
            pool.close()


async def board(pool: FalkorPool, ops_graph: str = GRAPH_OPS, kep_graph: str = GRAPH_KEP) -> dict[str, Any]:
    """Read model for `GET /agents/board`; missing graphs read as empty lists."""
    graphs = await pool.ping()

    async def rows(graph: str, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        out = await pool.ro_query(graph, query, params)
        return out.as_dicts()

    result: dict[str, Any] = {"agents": [], "tasks": [], "handoffs_last_hour": [], "drafts": [], "findings_recent": []}
    if ops_graph in graphs:
        result["agents"] = await rows(ops_graph, BOARD_AGENTS)
        result["tasks"] = await rows(ops_graph, BOARD_TASKS)
        result["handoffs_last_hour"] = await rows(ops_graph, BOARD_HANDOFFS, {"since": int(time.time()) - 3600})
        result["drafts"] = await rows(ops_graph, BOARD_DRAFTS)
    if kep_graph in graphs:
        result["findings_recent"] = await rows(kep_graph, BOARD_FINDINGS)
    return result
