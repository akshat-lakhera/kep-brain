"""Tool 2 `get_kep`: the KEP card with its one-hop context (03 §15.1).

State edges are filtered to the open interval (`valid_to` = sentinel), so
the card shows what the current `kep.yaml`, PRR file and tracking issue say.
"""

from __future__ import annotations

from typing import Any

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows

OPEN_FINDING_STATES = ["open", "triaged", "drafted", "confirmed"]

CUR = "coalesce(r.valid_to, $open) = $open"

TEMPLATE = f"""
MATCH (k:KEP {{key: $key}})
RETURN k,
 substring(coalesce(k.summary, ''), 0, 700) AS summary,
 k.metadata_invalid_reasons AS metadata_invalid_reasons,
 [(k)-[r:OWNED_BY]->(s:SIG) WHERE {CUR} | s] AS owning_sig,
 [(s)-[r:PARTICIPATES]->(k) WHERE {CUR} | s] AS participating_sigs,
 [(p:Person)-[r:AUTHORED]->(k) WHERE {CUR} | p] AS authors,
 [(p:Person)-[r:REVIEWS]->(k) WHERE {CUR} | p] AS reviewers,
 [(p:Person)-[r:APPROVES]->(k) WHERE {CUR} | p] AS approvers,
 [(p:Person)-[r:PRR_APPROVED]->(k) WHERE {CUR} | {{person: p, stage: r.stage}}] AS prr_approvers,
 [(k)-[r:GATED_BY]->(g:FeatureGate) WHERE {CUR} | g] AS feature_gates,
 [(k)-[r:TARGETS]->(x:Release) WHERE {CUR} | {{release: x.key, stage: r.stage}}] AS targets,
 [(k)-[r:LATEST]->(x:Release) WHERE {CUR} | x.key] AS latest_release,
 [(k)-[r:TRACKED_BY]->(i:Issue) WHERE {CUR} | i] AS tracking_issue,
 [(k)-[r:REPLACES]->(o:KEP) WHERE {CUR} | {{kep: o, declared_by: r.declared_by}}] AS replaces,
 [(o:KEP)-[r:REPLACES]->(k) WHERE {CUR} | {{kep: o, declared_by: r.declared_by}}] AS replaced_by,
 [(k)-[r:SUPERSEDED_BY]->(o:KEP) WHERE {CUR} | {{kep: o, derived: r.derived}}] AS superseded_by,
 [(k)-[r:SEE_ALSO]->(o:KEP) WHERE {CUR} | o] AS see_also,
 [(k)-[:HAS_DOCUMENT]->(d:Document) | d] AS documents,
 [(f:Finding)-[:ABOUT]->(k) WHERE f.state IN $open_states | f] AS known_issues
LIMIT 1
"""


class GetKepParams(ToolParams):
    kep_ref: KepRef


class GetKep(Tool):
    name = "get_kep"
    description = (
        "The KEP card: current status, stage, milestones, owning and participating SIGs, authors, reviewers, "
        "approvers, PRR approvers per stage, feature gates, target releases, the tracking issue (state, labels, "
        "milestone), replaces/replaced-by/superseded-by/see-also KEPs, documents, and open findings (known_issues: "
        "context only, cite the underlying records instead). kep_ref is a number or a path; an ambiguous number "
        "returns candidates."
    )
    Params = GetKepParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: GetKepParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        rows = await run.query(TEMPLATE, {"key": res.key, "open_states": OPEN_FINDING_STATES}, limit=2)
        for row in rows:
            kep = row["k"]["key"]
            for s in row.get("owning_sig", []):
                run.add_path(kep, "OWNED_BY", s["key"])
            for i in row.get("tracking_issue", []):
                run.add_path(kep, "TRACKED_BY", i["key"])
            for r in row.get("replaces", []):
                run.add_path(kep, "REPLACES", r["kep"]["key"])
            for r in row.get("replaced_by", []):
                run.add_path(r["kep"]["key"], "REPLACES", kep)
            for pr in row.get("prr_approvers", []):
                run.add_path(pr["person"]["key"], "PRR_APPROVED", kep)
        return run.result(rows)
