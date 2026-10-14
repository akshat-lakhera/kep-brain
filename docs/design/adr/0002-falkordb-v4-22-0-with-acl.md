# ADR 0002 · Pin FalkorDB to `v4.22.0` (C engine) with password and ACL users

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Version pin fixed by the team; ACL layout awaiting ratification by H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Image per environment and the ACL user split: yes. Version pin: no |
| Related | `02-architecture.md` §4.5, §11.2, §11.7; ADR 0005, ADR 0022, ADR 0024 |

## Context

FalkorDB published v6.0.0 (Rust engine) on 2026-09-29 and v6.0.2 on 10-08; v4.22.0 (C engine) shipped 2026-09-30 (GitHub releases API). Many issues opened since 2026-09-28 are tagged "[Rust]" with crashes. The judged demo must stay up for days unattended. FalkorDB has no authentication by default; FalkorDB's own judge at a previous event praised "read-only connections with timeouts".

Docker Hub has `falkordb/falkordb:v4.22.0` (server + Browser on 3000) and `falkordb/falkordb-server:v4.22.0`; the Docker guide recommends `-server` for production (https://docs.falkordb.com/operations/docker). With `aclfile` set, the file is the single source of truth, must exist before start, and may hold `#<sha256>` hashed passwords; users live in memory until the file is reloaded or the server restarts (https://docs.falkordb.com/operations/durability/acl-persistence).

Two facts found in the 2026-10-12 review shape the user table:

- falkordb-py 1.7.1's `FalkorDB.__init__` runs `Is_Sentinel(conn)` and `Is_Cluster(conn)`, each calling `conn.info(section="server")` (VERIFIED at https://raw.githubusercontent.com/FalkorDB/falkordb-py/v1.7.1/falkordb/sentinel.py lines 5–7, `cluster.py` 8–10, `falkordb.py` 132 and 136). A user without `INFO` cannot construct a client.
- FalkorDB v4.22.0 registers `graph.DELETE` with key position 1 and `graph.CONSTRAINT` with key position 2 (VERIFIED, https://github.com/FalkorDB/FalkorDB/blob/v4.22.0/src/module.c lines 260–266, 292–298), so ACL key patterns apply to both commands.

## Decision

- Pin `falkordb/falkordb:v4.22.0` for development (Browser on `127.0.0.1:3001`, server on `127.0.0.1:6380`) and `falkordb/falkordb-server:v4.22.0` for production (no published port). Never `latest`.
- Authentication through `/var/lib/falkordb/data/users.acl`, written by the one-shot `acl-init` container from environment variables. `--requirepass` is not used in `aclfile` mode; `FALKORDB_ACL_MODE=single` remains the B4 fallback.
- Five users:

| User | Keys | Commands | Held by |
|---|---|---|---|
| `default` | `~*` | `+@all` | healthcheck, backup cron, rotation, operators |
| `kb_reader` | `~kep ~ops ~eval_baseline` | `+PING +CLIENT\|SETINFO +INFO +GRAPH.RO_QUERY` | `api`, `mcp` |
| `kb_memory` | `~mem:*` | `+PING +CLIENT\|SETINFO +INFO +GRAPH.QUERY +GRAPH.RO_QUERY +GRAPH.DELETE +GRAPH.CONSTRAINT` | `api` |
| `kb_ops` | `~ops` | `+PING +CLIENT\|SETINFO +INFO +GRAPH.QUERY +GRAPH.RO_QUERY` | `api` (ADR 0022) |
| `kb_writer` | `~*` | `+PING +CLIENT\|SETINFO +INFO +GRAPH.QUERY +GRAPH.RO_QUERY +GRAPH.LIST +GRAPH.DELETE +GRAPH.COPY +GRAPH.CONSTRAINT +GRAPH.EXPLAIN +GRAPH.PROFILE +GRAPH.SLOWLOG +GRAPH.INFO +GRAPH.MEMORY` | `worker` |

- `+INFO` on every role user, so the documented falkordb-py constructor works; `INFO` exposes server metadata, not keys or values. `/v1/meta` reads the FalkorDB version from the worker's `SyncRun`, so no api identity needs `GRAPH.INFO`.
- `+GRAPH.DELETE +GRAPH.CONSTRAINT` on `kb_memory`, confined by `~mem:*`, so "Forget everything" and the lazy `UNIQUE` constraints of a new memory graph work.
- Server flags: `REDIS_ARGS="--aclfile … --appendonly yes --appendfsync everysec --save 300 10 --maxmemory <2gb dev|3gb prod> --maxmemory-policy noeviction"`; `FALKORDB_ARGS="THREAD_COUNT 3 CACHE_SIZE 200 TIMEOUT_MAX 60000 TIMEOUT_DEFAULT 5000 QUERY_MEM_CAPACITY 268435456 RESULTSET_SIZE 20000 MAX_QUEUED_QUERIES 45"` (https://docs.falkordb.com/configuration).
- Volume mounted at `/var/lib/falkordb/data`, the documented data directory, not `/data`.
- **Rotation**: write new values; `docker compose run --rm acl-init`; `ACL LOAD` as `default` (restart `falkordb` if the `default` password changed); restart dependents; verify `ACL WHOAMI` and one query per role; rollback by restoring the previous values and repeating. Rehearsed in the CI compose job and once on the VM.
- Upgrade to 6.x only after the event, behind the same integration suite.

## Alternatives considered

- `falkordb/falkordb:latest` (6.0.2): two weeks old with open crash reports.
- `--requirepass` only, one shared user: loses the read-only guarantee at the database layer.
- Building role clients as `redis.Redis(username, password)` wrapped in `falkordb.Graph(client, name)` to skip the constructor's `INFO` probe (`Graph.__init__(self, client, name)` VERIFIED in `graph.py`): no extra grant, but couples the code to a constructor the client does not document as public. Kept as the fallback if `+INFO` is ever unacceptable.
- Running memory erasure in the worker as `kb_writer` through a `Task`: avoids the `kb_memory` grants but makes "Forget everything" asynchronous; rejected because the key pattern already confines the grants.
- `allkeys-lru` eviction: would silently evict whole graphs.

## Consequences

- Every role connection is tested under its real ACL in the compose job (construction plus one query), together with: `kb_memory` deletes its own graph (`GRAPH.LIST` checked as `default`), cannot delete `kep`, can create a constraint on a `mem:` graph and not on `kep`; `kb_reader` cannot run `GRAPH.QUERY` or read `mem:*`.
- Still UNVERIFIED until INF-02 (Oct 15): whether FalkorDB's internal `telemetry{<graph>}` keys need a key pattern for restricted users, and whether `%R~` exists in 4.22.0 (unused).

## Revision 2026-10-12

Four users became five (`kb_ops` added); `+INFO` added to every role user; `kb_memory` gained `+GRAPH.DELETE +GRAPH.CONSTRAINT`; `kb_reader` narrowed from `~*` to four graphs; dev ports, `maxmemory` and `MAX_QUEUED_QUERIES` aligned with `06` C9 and B18; the rotation procedure now reloads the ACL (design review R8, R9, R10, R13, R14).
