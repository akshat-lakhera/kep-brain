# ADR 0004 · Parameterized tool catalog instead of text-to-Cypher

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Principle fixed by the team; catalog contents awaiting ratification by H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Catalog contents yes; principle no |
| Related | `02-architecture.md` §6–§7; `03-graph-model.md` §15; ADR 0005, ADR 0009, ADR 0013, ADR 0025 |

## Context

The agents need graph access. Two shapes exist: the LLM writes Cypher (text-to-Cypher; FalkorDB's GraphRAG-SDK marks it experimental), or the LLM picks from typed tools, each bound to one Cypher template with named parameters. FalkorDB caches plans per query shape and recommends parameterized queries, which also "prevent Cypher injection attacks" (https://docs.falkordb.com/commands/graph.query). Parameters are not allowed in `LIMIT`/`SKIP` (FalkorDB-MCPServer README). Judges can read the catalog as "the Cypher queries the product depends on" (Rule 10).

## Decision

- One registry feeds the Q&A agent, `POST /v1/tools/{name}`, the MCP server (with the B17 exclusions) and the README's generated query section. Names, parameters and traversal shapes are those of `03-graph-model.md` §15 plus `recall_findings` (`02` §7.1).
- **v1 has 14 LLM-callable tools** (ADR 0025): `find_entities`, `get_kep`, `who_approves`, `who_owns`, `trace_decision`, `status_history`, `whats_changed`, `find_contradictions`, `kep_relations`, `path_between`, `rank_people`, `draft_stale_doc_issue`, `recall_memory`, `recall_findings`. Of the other 17 intents of `03` §15, two are system tools (`remember`, `coordinate`) and 15 are deferred by default (`02` §7.3). System tools `remember`, `coordinate` and `record_finding` are never LLM-callable.
- Each tool module has: a Pydantic parameter model (types, enums, bounded ints), a description written for the model, one Cypher template per limit variant with `$named` parameters, an evidence mapper (rows → evidence objects and paths) and the reader client only. Limits and depths select one of a few pre-written templates (`limit ∈ {5, 10, 20}`, `depth ∈ {1, 2}`).
- The hand-written Cypher templates (`find_contradictions`, `trace_decision`, `kep_relations`, `path_between`, and the `find_entities` nearest match) are written by hand by named team members (ADR 0026); agents write the models, mappers and tests around them.
- Tool definitions sent to the LLM carry `strict: true`; `tool_choice` stays `auto` (forced choice returns 400 on `claude-sonnet-5-5`).
- Algorithms are tools: `rank_people` reads or runs `algo.pageRank`/`algo.betweenness`; `path_between` runs `algo.SPpaths`.
- Text-to-Cypher is not available in any path, including admin paths.

## Alternatives considered

- Text-to-Cypher with schema prompt and read-only execution: non-deterministic query shapes, no plan-cache reuse; experimental upstream.
- FalkorDB MCP server's `query_graph_readonly`: safe by command type but free-form Cypher, which the team's fixed decision forbids in the main path.
- GraphRAG-SDK end to end: hides the graph behind the SDK's ontology; the product depends on our explicit model.
- All 29 intents in v1 (v1 of this ADR said 14, `03` grew to 29): a platform, not one job (`02` §1).

## Consequences

- New question types need a new tool module, not prompt tinkering.
- The README's query section is generated from the registry, one template per tool with its traversal explained.
- Judges attaching an MCP client see which tool the model picks for each question.

## Revision 2026-10-12

Catalog aligned with `03` §15 names and narrowed to 14 v1 tools; human-written judge-path templates; the admin text-to-Cypher escape hatch removed (design review R2, R6, R7).
