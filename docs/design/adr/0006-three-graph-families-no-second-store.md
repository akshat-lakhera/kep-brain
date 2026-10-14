# ADR 0006 · Graph families in FalkorDB and no second datastore

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 (file name kept for stable links; the title no longer says "three") |
| Veto-able | Graph naming yes; "no second store" no |
| Related | `02-architecture.md` §5, §14; `03-graph-model.md` §2; ADR 0011, ADR 0012, ADR 0024 |

## Context

Rules 2–3: "If the product still works once FalkorDB is taken out, the graph is decoration rather than the thing the product runs on." T02 asks for "Separate memory per user or tenant" and "Shared state and handoffs between agents". FalkorDB stores each graph as one key; `select_graph(name)` addresses it; `GRAPH.LIST` enumerates graphs; ACL key patterns restrict users to families of graphs. Graphs are isolated: no cross-graph edges or joins.

## Decision

- **`kep`**: the knowledge graph (public corpus, single tenant), names per `03-graph-model.md`; also holds `Finding` nodes, written only by the worker (ADR 0024).
- **`ops`**: sync runs and cursors, tasks, agents, handoffs, action drafts, eval runs and results, analytics and load-test runs, `BudgetDay`, `AuditEvent`.
- **`mem:<ULID>`**: one graph per user (episodic, semantic, procedural memory). Names validated by a full match of `^mem:[0-9A-Z]{26}$` before any `select_graph`; a read never creates a graph.
- **`eval_baseline`**: vector and full-text chunks with no relationships, for the honest baseline arms.
- The v1 staging graph for blue/green rebuilds is deferred (ADR 0008).
- Cross-graph references are natural keys (`label|key`, `request_id`), resolved by a second read.
- There is no other database: not SQLite, not Postgres, not Redis lists or streams on the same server. CI scans dependencies and imports for other drivers. Deletable caches that hold inputs (the git clone volume; the dev-only raw GitHub response cache) are allowed.

## Alternatives considered

- Postgres for sessions, cursors and findings, FalkorDB for knowledge: conventional, but turns FalkorDB into a side index; the host's unrelated Postgres on 5432 must not be touched either.
- One graph with `User` subtrees for memory: per-tenant isolation would depend on every query's `WHERE`; ACL cannot restrict by subtree.
- `Finding` nodes inside `kep`: in-graph traversal from a finding to its evidence, but LLM-written text and a second writer in the corpus graph, and findings would not survive a full reload (ADR 0024).

## Consequences

- Rule 3 in its honest form: nothing works without FalkorDB, and the parts that make the product's job explainable (lineage chains, shortest paths, centrality) could not move to a relational store without reimplementing graph algorithms in application code. `02-architecture.md` §14 lists, tool by tool, which features a relational or vector store could serve equally well; v1's claim that every component proves Rule 3 is withdrawn.
- "Forget me" is one `GRAPH.DELETE` (ADR 0011). `memory-gc` deletes graphs idle for 90 days.

## Revision 2026-10-12

Families grew from three to four (`eval_baseline`); findings are `Finding` nodes in `kep`, not a separate graph; the staging graph is deferred; the Rule 3 consequence now points at the substitution table instead of claiming every component is graph-native (design review R3, R4, R7).
