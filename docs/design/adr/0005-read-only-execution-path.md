# ADR 0005 · Read-only execution path for everything the LLM influences

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Partly superseded by ADR 0022 for the api's `ops` writes. Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Timeouts and budgets yes; the three-layer principle for LLM-callable reads no |
| Related | `02-architecture.md` §4.2, §6.2, §6.5; ADR 0002, ADR 0004, ADR 0022, ADR 0024 |

## Context

Anything an LLM influences must be unable to modify the graph, even if a template were wrong or a parameter malicious. `GRAPH.RO_QUERY` "will return an error if you attempt a write query" and accepts a per-query `timeout` (https://docs.falkordb.com/commands/graph.ro-query). `TIMEOUT_MAX`, `TIMEOUT_DEFAULT`, `QUERY_MEM_CAPACITY` and `RESULTSET_SIZE` bound every query (https://docs.falkordb.com/configuration). Redis ACL can grant a user only `GRAPH.RO_QUERY` (https://docs.falkordb.com/commands/acl).

## Decision

**For every LLM-callable tool and every read of `kep`, `ops` and `eval_baseline`: three layers, all mandatory.**

1. **Code**: tools execute only through `ro_query(template, params, timeout=2000)`; the reader client type exposes no write method.
2. **Database identity**: the connection is `kb_reader` (`+GRAPH.RO_QUERY`, plus `+PING +CLIENT|SETINFO +INFO` for connection setup; ADR 0002); a `GRAPH.QUERY` from it fails with `NOPERM`.
3. **Server limits**: `TIMEOUT_MAX 60000`, `TIMEOUT_DEFAULT 5000`, `QUERY_MEM_CAPACITY 268435456`, `RESULTSET_SIZE 20000`, `MAX_QUEUED_QUERIES 45`. Per-call timeout 2,000 ms for tools, 1,000 ms for memory recall, 60,000 ms only for worker analytics.

**Writes that exist in processes running an LLM loop**, each with its own identity and a weaker, explicitly stated guarantee (fixed templates whose parameters come from validated data, plus the identity's key scope, plus an import boundary that keeps the client out of the agent and tool packages):

- `api` → `mem:<uid>` as `kb_memory` (`~mem:*`): `remember`, fact deletion, forget, lazy schema; composed by code from the validated `Answer`.
- `api` → `ops` as `kb_ops` (`~ops`): four labels (ADR 0022).
- Freshness-agent verdicts → `Finding` nodes in `kep`, written by code in `worker` as `kb_writer`: findings composed by code from the validated verifier output (ADR 0024).

Only `worker` holds `kb_writer`. Its freshness role runs an LLM loop (06 §1.6 X1), but the model never writes: its verdict is schema-validated, and `Finding` nodes are written through fixed templates whose parameters come only from that validated verdict and the contradiction's keys. The planner and MCP processes hold no write grant on `kep`.

## Alternatives considered

- Application-level enforcement only (a regex rejecting write clauses): bypassable; the server already provides the guarantee.
- A read replica for all reads: doubles memory and adds lag to freshness; unnecessary at this scale.
- Routing every write through the worker (v1's position for `ops`): an extra internal service and token for four writes the api needs synchronously (B13).

## Consequences

- Integration and ACL tests: reader cannot `GRAPH.QUERY`; `RO_QUERY` with a write clause errors; a slow pattern hits the timeout; `kb_memory` cannot touch `kep`; `kb_ops` cannot write `kep`; import-graph tests keep `kb_ops` and `kb_memory` clients out of `app/agent` and `app/tools`.
- Timeouts surface as `graph_timeout` (504) with the tool name.

## Revision 2026-10-12

The guarantee is now stated per graph and per identity; the api's `ops` writes (ADR 0022) and the freshness agent's `Finding` writes (ADR 0024) are named with their weaker guarantee instead of being omitted; `+INFO` noted (design review R9, R13).
