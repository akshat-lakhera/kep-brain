# ADR 0014 · Graph algorithms: precomputed by the worker, with bounded live calls

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Yes (live-only is the alternative; the deferred community algorithms can be re-enabled) |
| Related | `02-architecture.md` §7, §14; `03-graph-model.md` §5.6, §14; `06-build-plan.md` B20; ADR 0004 |

## Context

T01 focus "Graph queries and algorithms as agent tools"; T03 "who knows what". Procedures (https://docs.falkordb.com/cypher/procedures, …/algorithms/*): `algo.pageRank(label, relationship-type)` takes one label and one relationship type; `algo.betweenness({nodeLabels, relationshipTypes, samplingSize, samplingSeed})` has a time-based seed unless one is set; `algo.WCC({nodeLabels, relationshipTypes})`; `algo.labelPropagation({nodeLabels, relationshipTypes, maxIterations})`; `algo.SPpaths({sourceNode, targetNode, relTypes, relDirection, pathCount, maxLen})`. Writing results as properties is a write, so it cannot run on the read-only path. `02` §14 identifies these algorithms as the clearest graph-native work in the product.

## Decision

- **Projection** (`03` §5.6): the worker materialises `(:Person)-[:COLLABORATED {weight}]->(:Person)` (co-involvement on the same KEP via authored, reviewed, approved, PRR-approved and commented edges, weights documented in `03`; bots excluded), because `algo.pageRank` takes one label and one relationship type. `derived = true` and the run id on every projected edge.
- **Precompute in v1**, after every sync that changed a `Person`, `KEP` or ticket: `algo.pageRank('Person', 'COLLABORATED')` → `Person.pagerank`; `algo.betweenness({nodeLabels: ['Person'], relationshipTypes: ['COLLABORATED'], samplingSize: 256, samplingSeed: 42})` → `Person.betweenness`. Each run is an `AnalyticsRun {algorithms, seed, duration_ms}` in `ops`; nodes carry `analytics_run_id`.
- **Live in v1** (read-only, bounded): `path_between` runs `algo.SPpaths` (`relDirection: 'both'`, `pathCount ≤ 3`, `maxLen ≤ 6`, reduced to 4 if the B20 measurement exceeds 2,000 ms p99). `rank_people(refresh=true)` runs pageRank or betweenness live without writing, admin token only (B20); on timeout it returns stored values with `stale_analytics = true`.
- **Deferred with their tools** (`community_of`, `bridge_people`, ADR 0025): `algo.WCC` and `algo.labelPropagation`, both on `{nodeLabels: ['Person'], relationshipTypes: ['COLLABORATED']}` and `{nodeLabels: ['KEP'], relationshipTypes: ['RELATED_KEP']}` (`03` §14), writing `wcc_id` and `lp_community_id`. They are not computed in v1, because no v1 tool reads them.
- `rank_people` always returns per-edge evidence counts next to the score.

## Alternatives considered

- Live algorithms only: betweenness over ≈ 3,000 people per question is slow and, without a seed, non-deterministic.
- Computing in application code (NetworkX): moves the graph's job out of FalkorDB; `02` §14 is built on the fact that it does not.
- Computing WCC and label propagation in v1 anyway: one call each, but dead data until a tool reads it.

## Consequences

- Rankings are reproducible (fixed seed, recorded run id).
- The README's FalkorDB depth table lists pageRank, betweenness and SPpaths as used in v1, with WCC and label propagation marked as not shipped.

> **Superseded content (v1 of this ADR).** v1 ran WCC over `KEP` with relationship types `REPLACES`, `SEE_ALSO` and `GATED_BY`; `GATED_BY` points from `KEP` to `FeatureGate` and is filtered out by `nodeLabels: ['KEP']`, so the call measured less than it claimed. `03` §14 uses the `RELATED_KEP` projection instead.

## Revision 2026-10-12

v1 algorithm set narrowed to what v1 tools read; WCC corrected to `RELATED_KEP` and deferred with label propagation; B20 bounds and admin-only refresh adopted (design review R6, R7).
