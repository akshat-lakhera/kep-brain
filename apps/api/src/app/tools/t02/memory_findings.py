"""Tools 27 `recall_memory` and 30 `recall_findings` (03 §15.3).

`recall_memory` reads the caller's own `mem:<ULID>` graph (episodes the
api remembered after validated answers). `recall_findings` reads the shared
`Finding` memory in `kep`. Both are context: a claim cites the `kep`
records they point at, never the finding or the episode.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows
from app.tools.t03.audit import ACTIVE_STATES, ALL_STATES, FindingKind

FindingState = Literal["open", "triaged", "drafted", "confirmed", "dismissed", "resolved_upstream", "active", "all"]

_PROJ = """
RETURN f AS finding, k AS kep,
 [(k)-[r:OWNED_BY]->(s:SIG) WHERE coalesce(r.valid_to, $open) = $open | s.key] AS sig,
 [(f)-[r:EVIDENCED_BY]->(e) | {node: e, evidence_kind: r.evidence_kind}] AS evidence
ORDER BY f.state, f.detected_at DESC, f.key"""


def _template(scope: str, limit: int) -> str:
    match = {
        "kep": "MATCH (:KEP {key: $key})<-[:ABOUT]-(f:Finding)\nWHERE f.state IN $states",
        "sig": "MATCH (f:Finding)\nWHERE f.state IN $states",
        "state": "MATCH (f:Finding)\nWHERE f.state IN $states",
    }[scope]
    sig_filter = "\nWHERE k.owning_sig = $sig" if scope == "sig" else ""
    return (
        f"{match} AND (size($kinds) = 0 OR f.kind IN $kinds)\n"
        f"MATCH (k:KEP {{key: f.kep_path}}){sig_filter}{_PROJ}\nLIMIT {limit}\n"
    )


TEMPLATES = {(s, n): _template(s, n) for s in ("kep", "sig", "state") for n in (10, 50)}


class RecallFindingsParams(ToolParams):
    kep_ref: KepRef | None = None
    sig: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,60}$")
    state: FindingState = "active"
    kinds: list[FindingKind] = Field(default_factory=list)
    limit: Literal[10, 50] = 10

    @model_validator(mode="after")
    def _one_scope(self) -> RecallFindingsParams:
        if self.kep_ref and self.sig:
            raise ValueError("give kep_ref or sig, not both")
        return self


class RecallFindings(Tool):
    name = "recall_findings"
    description = (
        "What the organisation already recorded as wrong or inconsistent (shared Finding memory written by the "
        "detector and the freshness agent): by KEP, by SIG or by state, with each finding's two sides, state, "
        "triage verdict and the evidence records. Findings are context: cite the KEP, issue or document records."
    )
    Params = RecallFindingsParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: RecallFindingsParams = params
        run = Run(ctx)
        if p.state == "active":
            states = ACTIVE_STATES
        elif p.state == "all":
            states = ALL_STATES
        else:
            states = [p.state]
        args: dict[str, Any] = {"states": states, "kinds": list(p.kinds)}
        if p.kep_ref:
            res = await resolve_kep(run, p.kep_ref)
            if res.key is None:
                return run.result(unresolved_rows(p.kep_ref, res))
            rows = await run.query(TEMPLATES[("kep", p.limit)], {**args, "key": res.key}, limit=p.limit)
        elif p.sig:
            rows = await run.query(TEMPLATES[("sig", p.limit)], {**args, "sig": p.sig}, limit=p.limit)
        else:
            rows = await run.query(TEMPLATES[("state", p.limit)], args, limit=p.limit)
        for row in rows:
            run.add_path(row["finding"]["key"], "ABOUT", row["kep"]["key"])
            for ev in row.get("evidence", []):
                run.add_path(row["finding"]["key"], "EVIDENCED_BY", ev["node"]["key"])
        return run.result(rows)


EPISODES = """
MATCH (e:Episode)
WHERE $query = '' OR toLower(e.question) CONTAINS $query
RETURN e.key AS request_id, e.question AS question, e.answer_summary AS answer_summary,
 e.abstained AS abstained, e.evidence_keys AS evidence_keys, e.created_at_iso AS created_at
ORDER BY e.created_at DESC, e.key
LIMIT 20
"""

PROCEDURES = """
MATCH (pr:Procedure)
RETURN pr.key AS key, pr.tool_sequence AS tool_sequence, pr.success_count AS success_count
ORDER BY pr.success_count DESC, pr.key
LIMIT 10
"""


class RecallMemoryParams(ToolParams):
    kind: Literal["episodic", "procedural", "all"] = "all"
    query: str = Field(default="", max_length=200)


class RecallMemory(Tool):
    name = "recall_memory"
    description = (
        "What this user asked before (their own memory graph): earlier questions with a short answer summary and "
        "the graph keys the answer cited, and which tool sequences worked. Context only; re-query the graph "
        "with the keys to cite anything."
    )
    Params = RecallMemoryParams
    on_mcp = False

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: RecallMemoryParams = params
        run = Run(ctx)
        if not ctx.memory_id:
            return run.result([{"memory": "none", "reason": "no memory id on this request"}])
        from app.memory.store import memory_graph_name

        mem_ctx = ToolContext(pool=ctx.pool, graph=memory_graph_name(ctx.memory_id), memory_id=ctx.memory_id)
        mem_run = Run(mem_ctx)
        graphs = await ctx.pool.ping()
        if mem_ctx.graph not in graphs:
            return run.result([{"memory": "empty"}])
        rows: list[dict[str, Any]] = []
        if p.kind in ("episodic", "all"):
            for r in await mem_run.query(EPISODES, {"query": p.query.lower()}, limit=20):
                rows.append({"episode": r})
        if p.kind in ("procedural", "all"):
            for r in await mem_run.query(PROCEDURES, limit=10):
                rows.append({"procedure": r})
        out = mem_run.result(rows)
        out.evidence = []  # memory is never evidence (02 §6.2 item 5)
        return out
