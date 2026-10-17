"""`who_knows`: who has worked on a topic, a KEP or a SIG, ranked, with the edges that show it.

Scope is a set of KEPs: one KEP (`topic_or_kep` is a number or path), the KEPs
whose title, summary or README sections match a term (full-text), or a whole
SIG; `sig` also narrows a term scope. Inside the scope every person gets a
weighted degree over distinct (relationship, KEP) pairs:

    AUTHORED 3, APPROVES 3, PRR_APPROVED 2, REVIEWS 2 (kep.yaml edges into the KEP)
    SUBMITTED 1 (a review on a pull request that evidences a Decision about the KEP)
    COMMENTED 1 (an /lgtm or /approve comment that evidences such a Decision)

PageRank: FalkorDB 4.22's `algo.pageRank(label, relationshipType)` takes one
node label and one relationship type and cannot be restricted to a subgraph,
so it cannot rank people over the six edge types of one scope. The tool
reports, per ranked person, `decision_pagerank` = `algo.pageRank(null,
'DECIDED_BY')` over the whole graph (Decision → Person; a person's share of
all derived decisions), and `metric='pagerank'` orders the top scoped
candidates by it. Bots (`is_bot`) are excluded.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.tools.base import Run, SigKey, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import _coerce, resolve_kep, unresolved_rows
from app.tools.t03.find_entities import fulltext_term

WEIGHTS: dict[str, int] = {
    "AUTHORED": 3,
    "APPROVES": 3,
    "PRR_APPROVED": 2,
    "REVIEWS": 2,
    "SUBMITTED": 1,
    "COMMENTED": 1,
}
TERM_KEP_LIMIT = 20
CANDIDATES = 50

TERM_KEPS = f"""
CALL db.idx.fulltext.queryNodes('KEP', $term) YIELD node, score
WHERE $sig = '' OR node.owning_sig = $sig
RETURN node.key AS key, score
ORDER BY score DESC, key
LIMIT {TERM_KEP_LIMIT}
"""

TERM_SECTIONS = f"""
CALL db.idx.fulltext.queryNodes('Section', $term) YIELD node, score
WITH node.kep_path AS key, max(score) AS score
MATCH (k:KEP {{key: key}})
WHERE $sig = '' OR k.owning_sig = $sig
RETURN key, score
ORDER BY score DESC, key
LIMIT {TERM_KEP_LIMIT}
"""

SIG_KEPS = """
MATCH (k:KEP {owning_sig: $sig})
RETURN k.key AS key
ORDER BY key
LIMIT 400
"""

_CASE = " ".join(f"WHEN '{rel}' THEN {w}" for rel, w in WEIGHTS.items())


def _rank_template(limit: int) -> str:
    return f"""
CALL {{
  MATCH (p:Person)-[r:AUTHORED|APPROVES|PRR_APPROVED|REVIEWS]->(k:KEP)
  WHERE k.key IN $keys
  RETURN p, type(r) AS rel, k, null AS via, null AS d
  UNION ALL
  MATCH (p:Person)-[:SUBMITTED]->(x:Review)<-[:EVIDENCED_BY]-(d:Decision)-[:ABOUT]->(k:KEP)
  WHERE k.key IN $keys
  RETURN p, 'SUBMITTED' AS rel, k, x AS via, d
  UNION ALL
  MATCH (p:Person)-[:COMMENTED]->(x:Comment)<-[:EVIDENCED_BY]-(d:Decision)-[:ABOUT]->(k:KEP)
  WHERE k.key IN $keys
  RETURN p, 'COMMENTED' AS rel, k, x AS via, d
}}
WITH p, rel, k, collect(via)[0] AS via, collect(d)[0] AS d
WHERE coalesce(p.is_bot, false) = false
WITH p, rel, k, via, d, CASE rel {_CASE} ELSE 0 END AS w
ORDER BY w DESC, k.key
WITH p, sum(w) AS score, count(DISTINCT k) AS keps, collect(rel) AS rels,
     collect({{rel: rel, kep: k, via: via, decision: d.key}})[0..4] AS edges
RETURN p AS person, score, keps,
       [t IN {list(WEIGHTS)} | {{rel: t, n: size([x IN rels WHERE x = t])}}] AS by_rel, edges
ORDER BY score DESC, keps DESC, p.key
LIMIT {limit}
"""


RANK = {n: _rank_template(n) for n in (5, 10, 20, CANDIDATES)}

PAGERANK = """
MATCH (node:Person)
WHERE node.key IN $people
RETURN node.key AS person, coalesce(node.pagerank, 0.0) AS score
LIMIT 60
"""


class WhoKnowsParams(ToolParams):
    topic_or_kep: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        description="A KEP number or path, or a topic term; optional when sig is given",
    )
    sig: SigKey | None = Field(default=None, description="Scope to one SIG key")
    metric: Literal["weighted_degree", "pagerank"] = "weighted_degree"
    limit: Literal[5, 10, 20] = 10

    @field_validator("topic_or_kep", mode="before")
    @classmethod
    def _number(cls, v: Any) -> Any:
        return str(v) if isinstance(v, int) and not isinstance(v, bool) else v

    @model_validator(mode="after")
    def _scope(self) -> WhoKnowsParams:
        if not self.topic_or_kep and not self.sig:
            raise ValueError("give topic_or_kep, sig, or both")
        if self.topic_or_kep and _kep_ref(self.topic_or_kep) is None and fulltext_term(self.topic_or_kep) is None:
            raise ValueError("topic_or_kep has no searchable words")
        return self


def _kep_ref(text: str) -> str | None:
    try:
        return _coerce(text)
    except ValueError:
        return None


class WhoKnows(Tool):
    name = "who_knows"
    description = (
        "Who knows a topic, a KEP or a SIG: people ranked by weighted involvement in the KEPs in scope (authored 3, "
        "approves 3, PRR-approved 2, reviews 2, reviewed or /approve-commented a PR behind a decision 1), with "
        "the evidence edges (KEP, review/comment, decision) and decision_pagerank (algo.pageRank over "
        "Decision→Person DECIDED_BY edges, whole graph). topic_or_kep = KEP number/path or a term; sig optional."
    )
    Params = WhoKnowsParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: WhoKnowsParams = params
        run = Run(ctx)
        sig = p.sig or ""
        scope: dict[str, Any] = {"sig": p.sig}
        keys: list[str]
        ref = _kep_ref(p.topic_or_kep) if p.topic_or_kep else None
        if ref is not None:
            res = await resolve_kep(run, ref)
            if res.key is None:
                return run.result(unresolved_rows(ref, res))
            keys = [res.key]
            scope["kep"] = res.key
        elif p.topic_or_kep:
            term = fulltext_term(p.topic_or_kep) or ""
            hits = await run.query(TERM_KEPS, {"term": term, "sig": sig}, limit=TERM_KEP_LIMIT + 1)
            hits += await run.query(TERM_SECTIONS, {"term": term, "sig": sig}, limit=TERM_KEP_LIMIT + 1)
            keys = list(dict.fromkeys(h["key"] for h in hits))
            scope["term"] = term
        else:
            keys = [r["key"] for r in await run.query(SIG_KEPS, {"sig": sig}, limit=400)]
        scope["keps_in_scope"] = len(keys)
        run.truncated = False
        if not keys:
            return run.result([{"scope": scope, "people": 0}])

        fetch = CANDIDATES if p.metric == "pagerank" else p.limit
        people = await run.query(RANK[fetch], {"keys": keys}, limit=fetch)
        pr_rows = await run.query(PAGERANK, {"people": [r["person"]["key"] for r in people]}, limit=61)
        pagerank = {r["person"]: r["score"] for r in pr_rows}
        for row in people:
            row["decision_pagerank"] = round(float(pagerank.get(row["person"]["key"], 0.0)), 6)
            row["by_rel"] = {b["rel"]: b["n"] for b in row["by_rel"] if b["n"]}
        if p.metric == "pagerank":
            people.sort(key=lambda r: (-r["decision_pagerank"], -r["score"], r["person"]["key"]))
            run.truncated = len(people) > p.limit
            people = people[: p.limit]
        for row in people:
            pk = row["person"]["key"]
            for e in row["edges"]:
                kep = e["kep"]["key"]
                via = e.get("via")
                if via and e.get("decision"):
                    run.add_path(pk, e["rel"], via["key"], "EVIDENCED_BY", e["decision"], "ABOUT", kep)
                else:
                    run.add_path(pk, e["rel"], kep)
                # Nodes are already in `evidence`; edges keep only what cites them.
                e["kep"] = _ref(e["kep"])
                if via:
                    e["via"] = _ref(via)
        summary = {
            "scope": scope,
            "metric": p.metric,
            "weights": WEIGHTS,
            "pagerank": "algo.pageRank(null, 'DECIDED_BY') over the whole graph",
        }
        return run.result([summary, *people])


def _ref(node: dict[str, Any]) -> dict[str, Any]:
    return {k: node[k] for k in ("key", "title", "url", "evidence_id") if k in node}
