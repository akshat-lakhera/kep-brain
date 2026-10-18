"""`get_graph_schema` (MCP and `/v1/tools`, not the planner): labels, relationship types, indexes and constraints."""

from __future__ import annotations

from typing import Any

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult

LABELS = "CALL db.labels() YIELD label RETURN label ORDER BY label"
CONSTRAINTS = (
    "CALL db.constraints() YIELD type, label, properties, entitytype, status "
    "RETURN type, label, properties, entitytype, status ORDER BY label"
)
RELS = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
INDEXES = "CALL db.indexes() YIELD label, properties, types RETURN label, properties, types ORDER BY label"


class GetGraphSchemaParams(ToolParams):
    pass


class GetGraphSchema(Tool):
    name = "get_graph_schema"
    description = (
        "The graph's schema: node labels, relationship types and indexes (range and full-text) and "
        "constraints with their properties. Every node has key, url/source_url; state edges carry valid_from/valid_to."
    )
    Params = GetGraphSchemaParams
    llm_callable = False

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        run = Run(ctx)
        labels = [r["label"] for r in await run.query(LABELS, limit=500)]
        rels = [r["relationshipType"] for r in await run.query(RELS, limit=500)]
        indexes = await run.query(INDEXES, limit=500)
        constraints = await run.query(CONSTRAINTS, limit=500)
        run.truncated = False
        return run.result(
            [{"labels": labels, "relationship_types": rels, "indexes": indexes, "constraints": constraints}]
        )
