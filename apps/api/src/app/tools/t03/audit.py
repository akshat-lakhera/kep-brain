"""Tools 12 `find_contradictions` and 13 `kep_relations` (03 §15.1, §7.5).

`find_contradictions` reads the `Finding` nodes the detector wrote for the
five predicates of 03 §7.5 and returns, for each, both disagreeing sides
with their source URLs plus the KEP and its tracking issue as citable
records. The finding text itself is context; the citable evidence is the
KEP, the issue and the other records the finding points at.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schema.labels import FINDING_KINDS
from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows

FindingKind = Literal[
    "active_status_closed_issue",
    "terminal_status_future_targets",
    "one_sided_replacement",
    "stage_mismatch",
    "milestone_mismatch",
]
assert set(FindingKind.__args__) == set(FINDING_KINDS)  # type: ignore[attr-defined]

ACTIVE_STATES = ["open", "triaged", "drafted", "confirmed"]
ALL_STATES = [*ACTIVE_STATES, "dismissed", "resolved_upstream"]

_PROJECTION = """
RETURN f AS finding, k AS kep,
 [(k)-[r:TRACKED_BY]->(i:Issue) WHERE coalesce(r.valid_to, $open) = $open | i] AS tracking_issue,
 [(f)-[r:EVIDENCED_BY]->(e) | {node: e, evidence_kind: r.evidence_kind}] AS evidence
ORDER BY f.kind, k.key, f.key"""


def _corpus(limit: int) -> str:
    return f"""
MATCH (f:Finding)
WHERE f.state IN $states AND (size($kinds) = 0 OR f.kind IN $kinds)
MATCH (k:KEP {{key: f.kep_path}})
WHERE $sig = '' OR k.owning_sig = $sig{_PROJECTION}
LIMIT {limit}
"""


def _for_kep(limit: int) -> str:
    return f"""
MATCH (:KEP {{key: $key}})<-[:ABOUT]-(f:Finding)
WHERE f.state IN $states AND (size($kinds) = 0 OR f.kind IN $kinds)
MATCH (k:KEP {{key: f.kep_path}}){_PROJECTION}
LIMIT {limit}
"""


CORPUS = {n: _corpus(n) for n in (20, 50, 100)}
FOR_KEP = {n: _for_kep(n) for n in (20, 50, 100)}

COUNTS = """
MATCH (f:Finding)
WHERE f.state IN $states AND (size($kinds) = 0 OR f.kind IN $kinds)
MATCH (k:KEP {key: f.kep_path})
WHERE $sig = '' OR k.owning_sig = $sig
RETURN f.kind AS kind, count(f) AS findings, count(DISTINCT k) AS keps
ORDER BY kind
"""


class FindContradictionsParams(ToolParams):
    kep_ref: KepRef | None = Field(default=None, description="Scope to one KEP (number or path)")
    sig: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,60}$", description="Scope to one SIG key")
    kinds: list[FindingKind] = Field(default_factory=list, description="Predicates; empty means all five")
    include_closed: bool = Field(default=False, description="Also return dismissed and resolved findings")
    limit: Literal[20, 50, 100] = 20


class FindContradictions(Tool):
    name = "find_contradictions"
    description = (
        "Where a KEP's sources disagree (scope: whole corpus, a SIG, or one KEP). Five predicates: "
        "active_status_closed_issue (kep.yaml provisional/implementable but tracking issue closed), "
        "terminal_status_future_targets (withdrawn/deferred/replaced KEP still targets future releases), "
        "one_sided_replacement (a successor declares replaces but the predecessor has no superseded-by), "
        "stage_mismatch (kep.yaml stage vs closed issue's stage label), milestone_mismatch (latest-milestone vs "
        "issue milestone). Each hit: side a and side b with values and URLs, suggested fix, the KEP and its "
        "tracking issue as citable records, plus counts per kind. Use for 'is this metadata current?'."
    )
    Params = FindContradictionsParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: FindContradictionsParams = params
        run = Run(ctx)
        states = ALL_STATES if p.include_closed else ACTIVE_STATES
        args: dict[str, Any] = {"states": states, "kinds": list(p.kinds), "sig": p.sig or ""}
        if p.kep_ref:
            res = await resolve_kep(run, p.kep_ref)
            if res.key is None:
                return run.result(unresolved_rows(p.kep_ref, res))
            hits = await run.query(FOR_KEP[p.limit], {**args, "key": res.key}, limit=p.limit)
            counts: list[dict[str, Any]] = []
            if not hits:
                hits = [{"kep": res.candidates[0], "contradictions": 0}]
        else:
            hits = await run.query(CORPUS[p.limit], args, limit=p.limit)
            counts = await run.query(COUNTS, args, limit=10)
        for h in hits:
            if "finding" not in h:
                continue
            fk = h["finding"]["key"]
            run.add_path(fk, "ABOUT", h["kep"]["key"])
            for ev in h.get("evidence", []):
                run.add_path(fk, "EVIDENCED_BY", ev["node"]["key"])
            for i in h.get("tracking_issue", []):
                run.add_path(h["kep"]["key"], "TRACKED_BY", i["key"])
        rows: list[dict[str, Any]] = []
        if counts:
            rows.append({"counts_by_kind": counts, "total": sum(c["findings"] for c in counts)})
        rows.extend(hits)
        return run.result(rows)


RelType = Literal["REPLACES", "SUPERSEDED_BY", "SEE_ALSO"]
_ARROWS = {"both": ("-", "-"), "outgoing": ("-", "->"), "incoming": ("<-", "-")}


def _relations_template(types: tuple[str, ...], depth: int, direction: str) -> str:
    left, right = _ARROWS[direction]
    rels = "|".join(types)
    return f"""
MATCH p = (k:KEP {{key: $key}}){left}[:{rels}*1..{depth}]{right}(m:KEP)
WHERE m <> k AND all(r IN relationships(p) WHERE coalesce(r.valid_to, $open) = $open)
WITH m, p ORDER BY length(p)
WITH m, collect(p)[0] AS p
RETURN length(p) AS depth, m AS kep, p AS path,
 [r IN relationships(p) | {{type: type(r), from: startNode(r).key, to: endNode(r).key,
   declared_by: r.declared_by, derived: r.derived}}] AS via,
 [(m)-[o:OWNED_BY]->(s:SIG) WHERE coalesce(o.valid_to, $open) = $open | s.key] AS owning_sig,
 [(s)-[o:PARTICIPATES]->(m) WHERE coalesce(o.valid_to, $open) = $open | s.key] AS participating,
 [(m)-[o:TRACKED_BY]->(i:Issue) WHERE coalesce(o.valid_to, $open) = $open | i] AS tracking_issue,
 [(f:Finding)-[:ABOUT]->(m) WHERE f.state IN $states | {{kind: f.kind, state: f.state}}] AS open_findings
ORDER BY depth, m.key
LIMIT 200
"""


class KepRelationsParams(ToolParams):
    kep_ref: KepRef
    mode: Literal["family", "lineage"] = Field(
        default="family",
        description="family: direct replaces/superseded-by/see-also neighbours; lineage: replacement chains",
    )
    depth: int = Field(default=1, ge=1, le=3, description="Hops (lineage only; family is always 1)")
    types: list[RelType] = Field(default_factory=list, description="Edge types; empty = mode default")
    direction: Literal["both", "outgoing", "incoming"] = "both"


class KepRelations(Tool):
    name = "kep_relations"
    description = (
        "A KEP's family and decision lineage over REPLACES (successor → predecessor), SUPERSEDED_BY (predecessor → "
        "successor; derived=true when only the successor declared it) and SEE_ALSO. mode=family returns direct "
        "neighbours; mode=lineage follows replacement chains up to depth 3. Each reached KEP has its status, "
        "stage, owning SIG, tracking issue, the edge path from the root and open findings. Use for 'which KEPs "
        "does X replace' and 'what became of Y'."
    )
    Params = KepRelationsParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: KepRelationsParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        if p.mode == "family":
            types = tuple(p.types) or ("REPLACES", "SUPERSEDED_BY", "SEE_ALSO")
            depth = 1
        else:
            types = tuple(p.types) or ("REPLACES", "SUPERSEDED_BY")
            depth = p.depth
        ordered = tuple(t for t in ("REPLACES", "SUPERSEDED_BY", "SEE_ALSO") if t in types)
        template = _relations_template(ordered, depth, p.direction)
        hops = await run.query(template, {"key": res.key, "states": ACTIVE_STATES}, limit=200)
        for h in hops:
            if isinstance(h.get("path"), list):
                run.paths.append(h["path"])
        root = {"root": res.candidates[0], "reached": len(hops)}
        return run.result([root, *hops])
