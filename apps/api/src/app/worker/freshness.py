"""Freshness agent: advisory LLM triage of open `Finding`s (03 §4.7, ADR 0024).

The model sees only evidence rows read from the graph and returns a verdict, a short assessment citing evidence
ids, a suggested fix and a confidence. Code validates the answer: every cited id must belong to the rows it was
given, or the answer is discarded and the finding stays `open`. A verdict is advice; nothing becomes `confirmed`
here, a human does that.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog
from falkordb import Node

from app.agent.provider import call_with_policy_sync, cost_usd, model_chain, sync_client
from app.db.falkordb import GRAPH_KEP, GRAPH_OPS, FalkorPool, Role
from app.db.results import node_evidence
from app.settings import Settings

log = structlog.get_logger(__name__)

VERDICTS = ("confirmed", "false_positive", "needs_human")
FIXES = (
    "set_status_implemented",
    "set_status_withdrawn_or_deferred",
    "add_superseded_by",
    "update_latest_milestone",
    "update_stage",
    "remove_future_milestones",
    "other",
)
ASSESSMENT_MAX = 600
CITATION = re.compile(r"\[([a-z2-7]{12})\]")
URL = re.compile(r"https?://[^\s)\]>\"']+")
EVIDENCE_PROPS: dict[str, tuple[str, ...]] = {
    "KEP": ("number", "title", "status", "stage", "latest_milestone", "owning_sig", "last_updated"),
    "Issue": ("title", "state", "state_reason", "closed_at_iso", "labels_current", "milestone_current"),
    "Document": ("kind", "path", "title"),
    "StatusChange": ("kind", "field", "op", "from_value", "to_value", "at_iso", "actor_login"),
}

SYSTEM_PROMPT = (
    "You triage one suspected contradiction between public records of the Kubernetes enhancement process. "
    "You are given the two disagreeing sides and evidence rows, each with an evidence_id. Use only those rows. "
    "Decide: confirmed (the records really disagree and one is out of date), false_positive (the records are "
    "consistent once read correctly), or needs_human (the rows are not enough to decide). "
    "Write an assessment of at most 500 characters. Every factual statement must cite the evidence row it comes "
    "from as [evidence_id], copied exactly. Do not cite anything else and do not invent URLs. "
    'Reply with one JSON object: {"triage_verdict": one of confirmed|false_positive|needs_human, '
    '"assessment": string, "suggested_fix": one of ' + "|".join(FIXES) + ', "confidence": number from 0 to 1}.'
)

GATHER = """
MATCH (f:Finding {key: $key})-[:ABOUT]->(k:KEP)
OPTIONAL MATCH (f)-[:EVIDENCED_BY]->(ev)
OPTIONAL MATCH (k)-[:TRACKED_BY]->(i:Issue)
RETURN f.kind AS kind, f.state AS state, f.a_label AS a_label, f.a_value AS a_value, f.a_url AS a_url,
 f.b_label AS b_label, f.b_value AS b_value, f.b_url AS b_url, f.suggested_fix AS suggested_fix,
 f.triage_verdict AS verdict, f.assessment AS assessment, f.triage_confidence AS confidence,
 k AS kep, collect(DISTINCT ev) AS evidence, collect(DISTINCT i) AS issues
"""
OPEN_KEYS = "MATCH (f:Finding {state: 'open'}) RETURN f.key ORDER BY f.key"
WRITE_TRIAGE = """
MATCH (f:Finding {key: $key, state: 'open'})
SET f.triage_verdict = $verdict, f.assessment = $assessment, f.triage_suggested_fix = $fix,
 f.triage_confidence = $confidence, f.triage_model = $model, f.triage_evidence_ids = $ids,
 f.triaged_at = $now, f.triaged_at_iso = $now_iso, f.state = 'triaged'
RETURN f.key
"""
SPEND_READ = "MATCH (b:BudgetDay {key: $key}) RETURN b.spent_usd_micros"
SPEND_ADD = """
MERGE (b:BudgetDay {key: $key})
SET b.spent_usd_micros = coalesce(b.spent_usd_micros, 0) + $micros, b.updated_at = $now
RETURN b.spent_usd_micros
"""


class TriageRejected(ValueError):
    """The model answer failed deterministic validation."""


@dataclass(frozen=True)
class EvidenceRow:
    evidence_id: str
    label: str
    key: str
    url: str
    props: dict[str, Any]

    def as_prompt(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "type": self.label, "key": self.key, "url": self.url, **self.props}


@dataclass(frozen=True)
class FindingContext:
    key: str
    kind: str
    state: str
    sides: dict[str, str]
    suggested_fix: str
    rows: list[EvidenceRow]
    verdict: str | None = None
    assessment: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Triage:
    verdict: str
    assessment: str
    suggested_fix: str
    confidence: float
    evidence_ids: list[str]


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class Llm(Protocol):
    model: str

    def complete(self, messages: list[dict[str, str]]) -> Completion: ...


class OpenAICompatibleLlm:
    """The cheap model through the shared client, limiter and retry/fallback policy of the agent provider."""

    def __init__(self, settings: Settings, http_client: Any = None) -> None:
        self.settings = settings
        self.model = settings.llm_model_cheap
        self._client = sync_client(settings, http_client)

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        def send(model: str) -> Any:
            params: Any = messages
            return self._client.chat.completions.create(
                model=model, messages=params, temperature=0, response_format={"type": "json_object"}
            )

        model, resp = call_with_policy_sync(self.settings, model_chain(self.settings, self.model), send)
        self.model = model
        usage = resp.usage
        return Completion(
            text=resp.choices[0].message.content or "" if resp.choices else "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )


def validate_triage(raw: str, rows: Sequence[EvidenceRow]) -> Triage:
    """Parse and check a model answer against the evidence it was given. Raises `TriageRejected`."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TriageRejected("not valid JSON") from exc
    if not isinstance(data, dict):
        raise TriageRejected("not a JSON object")
    verdict, fix = data.get("triage_verdict"), data.get("suggested_fix")
    assessment, confidence = data.get("assessment"), data.get("confidence")
    if verdict not in VERDICTS:
        raise TriageRejected("unknown triage_verdict")
    if fix not in FIXES:
        raise TriageRejected("unknown suggested_fix")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
        raise TriageRejected("confidence must be a number between 0 and 1")
    if not isinstance(assessment, str) or not assessment.strip():
        raise TriageRejected("assessment is empty")
    assessment = assessment.strip()
    if len(assessment) > ASSESSMENT_MAX:
        raise TriageRejected("assessment is longer than 600 characters")
    known = {r.evidence_id for r in rows}
    cited = list(dict.fromkeys(CITATION.findall(assessment)))
    if not cited:
        raise TriageRejected("assessment cites no evidence id")
    unknown = [c for c in cited if c not in known]
    if unknown:
        raise TriageRejected(f"assessment cites ids that were not given: {unknown}")
    allowed_urls = {r.url for r in rows}
    stray = [u for u in URL.findall(assessment) if u.rstrip(".,;") not in allowed_urls]
    if stray:
        raise TriageRejected(f"assessment contains urls that were not given: {stray}")
    return Triage(str(verdict), assessment, str(fix), float(confidence), cited)


def _row(node: Node) -> EvidenceRow | None:
    ev = node_evidence(node)
    if ev is None:
        return None
    wanted = EVIDENCE_PROPS.get(ev.label, ())
    props = {k: v for k, v in (node.properties or {}).items() if k in wanted and v is not None}
    return EvidenceRow(ev.evidence_id, ev.label, ev.key, ev.url, props)


def gather_context(pool: FalkorPool, finding_key: str, graph: str = GRAPH_KEP) -> FindingContext | None:
    out = pool.run_sync(Role.WRITER, graph, GATHER, {"key": finding_key}, read_only=True, timeout_ms=10000)
    if not out.rows:
        return None
    r = dict(zip(out.header, out.rows[0], strict=False))
    rows: dict[str, EvidenceRow] = {}
    for node in [r["kep"], *r["issues"], *r["evidence"]]:
        row = _row(node)
        if row is not None:
            rows.setdefault(row.evidence_id, row)
    sides = {k: str(r[k]) for k in ("a_label", "a_value", "a_url", "b_label", "b_value", "b_url")}
    return FindingContext(
        finding_key,
        r["kind"],
        r["state"],
        sides,
        r["suggested_fix"] or "other",
        list(rows.values()),
        r["verdict"],
        r["assessment"],
        r["confidence"],
    )


def build_messages(ctx: FindingContext) -> list[dict[str, str]]:
    payload = {
        "finding": {"kind": ctx.kind, "detector_suggested_fix": ctx.suggested_fix, **ctx.sides},
        "evidence": [r.as_prompt() for r in ctx.rows],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _budget_key(now: float) -> str:
    return "findings:" + datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")


def spent_today_usd(pool: FalkorPool, ops_graph: str = GRAPH_OPS) -> float:
    out = pool.run_sync(
        Role.WRITER, ops_graph, SPEND_READ, {"key": _budget_key(time.time())}, read_only=False, timeout_ms=5000
    )
    return (out.rows[0][0] if out.rows else 0) / 1_000_000


def budget_left(pool: FalkorPool, settings: Settings, ops_graph: str = GRAPH_OPS) -> bool:
    return spent_today_usd(pool, ops_graph) < settings.findings_agent_daily_usd


def _record_spend(pool: FalkorPool, ops_graph: str, usd: float) -> None:
    now = time.time()
    pool.run_sync(
        Role.WRITER,
        ops_graph,
        SPEND_ADD,
        {"key": _budget_key(now), "micros": round(usd * 1_000_000), "now": int(now)},
        read_only=False,
        timeout_ms=5000,
    )


def triage_finding(
    pool: FalkorPool,
    settings: Settings,
    finding_key: str,
    llm: Llm,
    *,
    kep_graph: str = GRAPH_KEP,
    ops_graph: str = GRAPH_OPS,
) -> dict[str, Any]:
    """Triage one open finding. Returns a result dict with `status` triaged, rejected or skipped."""
    ctx = gather_context(pool, finding_key, kep_graph)
    if ctx is None or ctx.state != "open":
        return {"finding": finding_key, "status": "skipped", "reason": "not an open finding"}
    completion = llm.complete(build_messages(ctx))
    cost = cost_usd(llm.model, completion.input_tokens, completion.output_tokens)
    _record_spend(pool, ops_graph, cost)
    try:
        triage = validate_triage(completion.text, ctx.rows)
    except TriageRejected as exc:
        log.warning("triage_rejected", finding=finding_key, reason=str(exc))
        return {"finding": finding_key, "status": "rejected", "reason": str(exc), "usd": cost}
    now = int(time.time())
    pool.run_sync(
        Role.WRITER,
        kep_graph,
        WRITE_TRIAGE,
        {
            "key": finding_key,
            "verdict": triage.verdict,
            "assessment": triage.assessment,
            "fix": triage.suggested_fix,
            "confidence": triage.confidence,
            "model": llm.model,
            "ids": triage.evidence_ids,
            "now": now,
            "now_iso": datetime.fromtimestamp(now, UTC).isoformat(),
        },
        read_only=False,
        timeout_ms=10000,
    )
    return {
        "finding": finding_key,
        "status": "triaged",
        "verdict": triage.verdict,
        "confidence": triage.confidence,
        "usd": cost,
        "assessment": triage.assessment,
    }


def run_freshness_once(
    settings: Settings,
    limit: int | None = None,
    *,
    llm: Llm | None = None,
    pool: FalkorPool | None = None,
    kep_graph: str = GRAPH_KEP,
    ops_graph: str = GRAPH_OPS,
) -> dict[str, Any]:
    """Triage open findings until `limit`, the daily spend cap, or the list runs out."""
    if not settings.findings_agent_enabled:
        return {"skipped": "findings_agent_enabled is false"}
    own_pool = pool is None
    pool = pool or FalkorPool(settings)
    try:
        agent = llm or OpenAICompatibleLlm(settings)
        keys = [r[0] for r in pool.run_sync(Role.WRITER, kep_graph, OPEN_KEYS, read_only=True, timeout_ms=10000).rows]
        results: list[dict[str, Any]] = []
        stopped = None
        for key in keys[:limit] if limit is not None else keys:
            if not budget_left(pool, settings, ops_graph):
                stopped = "daily_cap_reached"
                break
            results.append(triage_finding(pool, settings, key, agent, kep_graph=kep_graph, ops_graph=ops_graph))
        counts: dict[str, int] = {}
        for r in results:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        summary = {
            "open": len(keys),
            "attempted": len(results),
            "counts": counts,
            "usd": round(sum(r.get("usd", 0.0) for r in results), 6),
            "stopped": stopped,
            "results": results,
        }
        log.info("freshness_run", **{k: v for k, v in summary.items() if k != "results"})
        return summary
    finally:
        if own_pool:
            pool.close()
