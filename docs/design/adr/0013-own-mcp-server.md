# ADR 0013 · Own MCP server over the tool registry

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12; adopts `06-build-plan.md` B17). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Yes (FalkorDB's MCP server in read-only mode is the alternative; stdio-only is cut line L13) |
| Related | `02-architecture.md` §7.1–§7.2, §12; ADR 0004, ADR 0005, ADR 0024 |

## Context

T01 focus: "Tool selection through MCP". FalkorDB ships `@falkordb/mcpserver` 1.3.0 with `query_graph`, `query_graph_readonly`, `list_graphs`, `get_graph_schema` and related tools, a read-only switch, stdio or HTTP transport and bearer auth (https://github.com/FalkorDB/FalkorDB-MCPServer); its query tools accept free-form Cypher, which the team's fixed decision excludes from the main path. MCP specification revision 2026-07-28 defines stdio and Streamable HTTP (https://modelcontextprotocol.io/specification/latest). Python SDK `mcp` 2.3.0 (PyPI 2026-10-02).

## Decision

- `python -m app.mcp` runs an MCP server that exposes the read-only registry with the same Pydantic schemas and descriptions, plus `get_graph_schema` (labels, relationship types, indexes via `db.labels()`, `db.relationshipTypes()`, `db.indexes()`). v1 MCP tools (12): `find_entities`, `get_kep`, `who_approves`, `trace_decision`, `status_history`, `whats_changed`, `find_contradictions`, `kep_relations`, `path_between`, `rank_people`, `recall_findings`, `get_graph_schema`.
- **Never exposed**: `recall_memory` (MCP clients have no memory id), `remember`, `coordinate`, `record_finding`, `draft_stale_doc_issue`. A parity test asserts this exclusion list and that no tool input has a free-text field named or described as a query or Cypher.
- `recall_findings` is exposed on purpose: external agents read the same shared memory the Q&A agent reads (ADR 0024).
- Transport: Streamable HTTP on `:8765` behind Caddy at `/mcp`, `Authorization: Bearer <MCP_TOKEN>`; `MCP_TOKEN` is a **public, read-only judge token** published in `docs/MCP.md`, distinct from `ADMIN_TOKEN`, rate-limited per token and per IP, rotated after results; `Origin`/`Host` allow-list and a request-size limit; results carry `untrusted_content: true`. `--transport stdio` for local clients.
- Executes as `kb_reader` only.
- FalkorDB's MCP server is mentioned in the README as a complementary way to inspect the graph locally, in read-only mode, not as part of the product.

## Alternatives considered

- FalkorDB's MCP server as the product surface: zero code, but free-form Cypher contradicts the fixed decision and makes "which tool did the agent pick" meaningless.
- stdio only (cut line L13): no remote demo for judges.
- A TypeScript server: splits the registry across languages.

## Consequences

- One registry, three surfaces (agent, HTTP, MCP), with the exclusions tested.
- Judges attaching an MCP client see tool selection per question, and see shared findings produced by the freshness agent.

> **Superseded content (v1 of this ADR).** v1 exposed the full catalog including the memory tool and used a `KEPBRAIN_`-prefixed token variable; replaced as above (B2, B17).

## Revision 2026-10-12

Tool list per the v1 scope and B17 exclusions; `recall_findings` added; public judge token and its controls (design review R4, R6, R7).
