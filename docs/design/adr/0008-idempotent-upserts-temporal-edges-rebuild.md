# ADR 0008 · Idempotent MERGE upserts with content hashes, reified history and full reload

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 (file name kept for stable links) |
| Veto-able | Deferring the blue/green swap: yes. MERGE on natural keys: no |
| Related | `02-architecture.md` §5.1, §9.2–§9.3, §13.4; `03-graph-model.md` §3, §4.4, §7; ADR 0007 |

## Context

FalkorDB's judge praised "`MERGE` so imports can be re-run safely". `MERGE` matches or creates, supports `ON CREATE SET`/`ON MATCH SET`, and duplicates nodes when a whole path is merged with a missing element, so endpoints are merged separately (https://docs.falkordb.com/cypher/merge). Every write query is atomic and writes are serialised per graph (https://docs.falkordb.com/design/concurrency). `LIMIT` does not stop eager operations (…/cypher/known-limitations). Unique constraints need an exact-match index first and are created asynchronously (…/commands/graph.constraint-create). `03-graph-model.md` is authoritative for every label, key and edge name used here.

## Decision

- **Natural keys**: every node has one `key` string (`03` §3.1); KEP key = repository path `keps/<sig-dir>/<dir>` (numbers collide: 2133 twice, `0000` shared); Person key = lower-cased login. Range index on `key` and a `UNIQUE` constraint for every label; the worker waits for `db.constraints()` to report `OPERATIONAL` before loading.
- **Normalisation before MERGE** (`01` D5–D7; the map is hand-written by H-Data/Eval, ADR 0026): status and stage through an enum map with `*_raw` twins and `metadata_invalid`; references resolved by path → old filename → bare number → `ExternalRef`; inverse `SUPERSEDED_BY` derived; one-sided declarations flagged.
- **Upsert shape**: `UNWIND $rows` of 500, `MERGE` on `key`, `ON CREATE SET` the full row, `ON MATCH SET` only when `content_hash` differs (SHA-256 of the canonical row after PII scrubbing); edges merged in a separate clause between matched endpoints; `timeout = 30000`.
- **Reified history** (`03` §4.4, §7): one `StatusChange` node per field change from `kep.yaml` commits (key `sc:<KEP key>:<field>:<sha>`) and one per tracking-issue label or milestone event (key `ghe:<GraphQL event id>`), linked `KEP` → `CHANGED` → `StatusChange` → `IN_COMMIT` → `Commit` → `IN_PR` → `PullRequest`, `Issue` → `HAS_EVENT` → `StatusChange`, `Person` → `ACTED` → `StatusChange`, chained by `PREVIOUS` with `valid_from`/`valid_to` (sentinel `4102444800`). `Decision` nodes derived from them (`03` §8.2). A range index on `StatusChange.at` serves "what changed since".
- **State edges** carry `valid_from`, `valid_to`, `observed_at`, `source_url` (`MANDATORY` constraints on all 31 state-edge types). Removals close `valid_to`; nothing that was once true is deleted.
- **Soft deletes**: `archived = true`, `archived_at`; tools exclude archived nodes by default.
- **Incremental sync**: doc layer by `git diff` between `SyncCursor {key: enhancements_head}` and the new head; tickets by `since` and ETag cursors with a 60 s overlap and GraphQL re-queries of moved items.
- **Full reload** (a schema change during the event): `GRAPH.DELETE kep`, `schema apply`, `sync --full` on the dev machine, then re-seed the VM from the dump (`02` §13.4). The blue/green swap through a staging graph and `GRAPH.COPY` is deferred.

## Alternatives considered

- Blue/green swap (v1): seconds of unavailability instead of minutes, at the cost of twice the graph memory and a swap path to build and test; the VM never reloads in place (it is re-seeded from a dump), so the benefit does not appear in the judged deployment.
- `CREATE` with pre-deletion: a failure leaves a partial graph and breaks incremental sync.
- History as edge properties (v1): an edge cannot be cited or be the target of `EVIDENCED_BY`, and metadata changes and label events could not be ordered in one scan (`03` §17).

## Consequences

- Running `sync` twice is a no-op by construction; the integration test asserts identical counts and zero `ON MATCH` writes on the second pass.
- `status_history` and `whats_changed` are one indexed scan plus 1–3 hops.
- Tools take a `kep_ref` (number or path); an ambiguous number returns the candidate paths.

> **Superseded content (v1 of this ADR).** v1 modelled history as `CHANGED_BY {field, from, to, at}` edges from `KEP` to `Commit` and label history as `LabelEvent` nodes, with an index on `CHANGED_BY.at`. Both are replaced by `StatusChange` as described above (`03` §17).

## Revision 2026-10-12

Names aligned with `03` (`StatusChange`, `CHANGED`, `HAS_EVENT`, `IN_COMMIT`, `ACTED`, validity intervals); blue/green swap deferred in favour of a full reload plus dump re-seed; normalisation map owned by a human (design review R2, R6, R7).
