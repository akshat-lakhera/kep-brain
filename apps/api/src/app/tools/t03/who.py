"""Tools 5 `who_owns` and 6 `who_approves` (03 §15.1).

`who_approves` joins three independent sources for one KEP: the `kep.yaml`
approvers, the PRR approvers per stage, and the people the derived
`Decision` nodes name as having actually decided past transitions.
`who_owns` resolves directory ownership through OWNERS files when they are
loaded; when the graph holds no OWNERS data it says so instead of guessing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows

CUR = "coalesce(r.valid_to, $open) = $open"

APPROVES_TEMPLATE = f"""
MATCH (k:KEP {{key: $key}})
RETURN k,
 [(p:Person)-[r:APPROVES]->(k) WHERE {CUR} | p] AS declared_approvers,
 [(p:Person)-[r:PRR_APPROVED]->(k) WHERE {CUR} AND ($stage = '' OR r.stage = $stage)
   | {{person: p, stage: r.stage}}] AS prr_approvers,
 [(k)-[o:OWNED_BY]->(s:SIG)<-[r:CHAIRS|TECH_LEAD]-(p:Person) WHERE {CUR} AND coalesce(o.valid_to, $open) = $open
   | {{person: p, role: type(r), sig: s.key}}] AS sig_leads
LIMIT 1
"""

DECISIONS_TEMPLATE = """
MATCH (d:Decision {kep_path: $key})
WHERE $stage = '' OR d.stage = $stage OR d.stage IS NULL
WITH d ORDER BY d.decided_at, d.key LIMIT 50
RETURN d AS decision,
 [(d)-[r:DECIDED_BY]->(p:Person) | {person: p, role: r.role}] AS people,
 [(d)-[r:EVIDENCED_BY]->(e) | e] AS evidence
ORDER BY d.decided_at, d.key
"""


class WhoApprovesParams(ToolParams):
    kep_ref: KepRef
    stage: Literal["alpha", "beta", "stable"] | None = None


class WhoApproves(Tool):
    name = "who_approves"
    description = (
        "Who decides for a KEP: approvers declared in kep.yaml, PRR approvers per stage (alpha/beta/stable), the "
        "owning SIG's chairs and tech leads when loaded, and past_decisions: the derived Decision nodes with the "
        "people who actually approved/merged each recorded transition and their evidence (PRs, reviews, commits)."
    )
    Params = WhoApprovesParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: WhoApprovesParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        stage = p.stage or ""
        rows = await run.query(APPROVES_TEMPLATE, {"key": res.key, "stage": stage}, limit=2)
        decisions = await run.query(DECISIONS_TEMPLATE, {"key": res.key, "stage": stage}, limit=50)
        for row in rows:
            for a in row.get("declared_approvers", []):
                run.add_path(a["key"], "APPROVES", res.key)
            for a in row.get("prr_approvers", []):
                run.add_path(a["person"]["key"], "PRR_APPROVED", res.key)
            row["past_decisions"] = decisions
        for d in decisions:
            for person in d.get("people", []):
                run.add_path(d["decision"]["key"], "DECIDED_BY", person["person"]["key"])
        return run.result(rows)


OWNERS_TEMPLATE = """
MATCH (d:Document)
WHERE d.kind = 'owners' AND d.directory IN $paths
RETURN d,
 [(d)-[r:APPROVER|REVIEWER]->(p:Person) WHERE coalesce(r.valid_to, $open) = $open
   | {person: p, role: toLower(type(r))}] AS direct,
 [(d)-[r:APPROVER|REVIEWER]->(a:Alias)<-[m:MEMBER_OF]-(ap:Person)
   WHERE coalesce(r.valid_to, $open) = $open AND coalesce(m.valid_to, $open) = $open
   | {person: ap, role: toLower(type(r)), via_alias: a.key}] AS via_alias,
 [(d)-[r:APPLIES_LABEL]->(s:SIG) WHERE coalesce(r.valid_to, $open) = $open | s] AS sigs
ORDER BY size(d.directory) DESC, d.key
LIMIT 20
"""

KEP_OWNERS_TEMPLATE = f"""
MATCH (k:KEP {{key: $key}})
RETURN k,
 [(k)-[r:OWNED_BY]->(s:SIG) WHERE {CUR} | s] AS owning_sig,
 [(k)-[o:OWNED_BY]->(s:SIG)<-[r:CHAIRS|TECH_LEAD]-(p:Person) WHERE {CUR} AND coalesce(o.valid_to, $open) = $open
   | {{person: p, role: toLower(type(r)), sig: s.key}}] AS sig_leads,
 [(p:Person)-[r:APPROVES]->(k) WHERE {CUR} | {{person: p, role: 'kep_approver'}}] AS kep_approvers
LIMIT 1
"""

GATE_TEMPLATE = """
MATCH (g:FeatureGate {key: $gate})<-[r:GATED_BY]-(k:KEP)
WHERE coalesce(r.valid_to, $open) = $open
RETURN g, k
ORDER BY k.key
LIMIT 10
"""


def _directory_chain(path: str) -> list[str]:
    parts = [p for p in path.strip().strip("/").split("/") if p]
    chain = ["/".join(parts[:i]) for i in range(len(parts), 0, -1)]
    return chain + [""]


class WhoOwnsParams(ToolParams):
    kep_ref: KepRef | None = None
    directory_path: str | None = Field(default=None, max_length=300, description="kubernetes/kubernetes directory")
    feature_gate: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _exactly_one(self) -> WhoOwnsParams:
        given = [v for v in (self.kep_ref, self.directory_path, self.feature_gate) if v]
        if len(given) != 1:
            raise ValueError("give exactly one of kep_ref, directory_path, feature_gate")
        return self


class WhoOwns(Tool):
    name = "who_owns"
    description = (
        "Owners of a KEP (owning SIG, its chairs/tech leads when loaded, kep.yaml approvers), of a feature gate "
        "(via the KEP that introduces it) or of a source directory (OWNERS file approvers/reviewers, aliases "
        "expanded, nearest parent OWNERS file). Returns owners_data_loaded=false when the graph holds no OWNERS "
        "files for that path: then ownership is unknown, not empty."
    )
    Params = WhoOwnsParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: WhoOwnsParams = params
        run = Run(ctx)
        if p.directory_path:
            files = await run.query(OWNERS_TEMPLATE, {"paths": _directory_chain(p.directory_path)}, limit=20)
            if not files:
                return run.result([{"directory_path": p.directory_path, "owners_data_loaded": False, "owners": []}])
            nearest = files[0]
            owners = nearest.get("direct", []) + nearest.get("via_alias", [])
            for o in owners:
                run.add_path(nearest["d"]["key"], o["role"].upper(), o["person"]["key"])
            return run.result(
                [{"directory_path": p.directory_path, "owners_file": nearest["d"], "owners": owners,
                  "sigs": nearest.get("sigs", []), "owners_data_loaded": True}]
            )  # fmt: skip
        keys: list[str] = []
        rows: list[dict[str, Any]] = []
        if p.feature_gate:
            gate_rows = await run.query(GATE_TEMPLATE, {"gate": p.feature_gate}, limit=10)
            if not gate_rows:
                return run.result([{"feature_gate": p.feature_gate, "not_found": True}])
            for g in gate_rows:
                keys.append(g["k"]["key"])
                run.add_path(g["k"]["key"], "GATED_BY", g["g"]["key"])
        else:
            assert p.kep_ref is not None
            res = await resolve_kep(run, p.kep_ref)
            if res.key is None:
                return run.result(unresolved_rows(p.kep_ref, res))
            keys.append(res.key)
        for key in keys:
            for row in await run.query(KEP_OWNERS_TEMPLATE, {"key": key}, limit=2):
                for s in row.get("owning_sig", []):
                    run.add_path(key, "OWNED_BY", s["key"])
                rows.append(row)
        return run.result(rows)
