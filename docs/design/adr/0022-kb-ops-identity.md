# ADR 0022 · `kb_ops`: the api's four writes to `ops`

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (2026-10-12; records `06-build-plan.md` B13 as an architecture decision). Supersedes the parts of ADR 0005 and ADR 0012 that said the api never writes `ops`. Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-12 |
| Veto-able | Yes (alternative below) |
| Related | `02-architecture.md` §4.2, §6.5; `03-graph-model.md` §10; ADR 0002, ADR 0005, ADR 0012, ADR 0021 |

## Context

The api has four synchronous needs in `ops`: creating a queued `Task` ("Sync now", a Q&A answer that saw an unseen contradiction), creating an `ActionDraft` and compare-and-setting its `status` on confirm, incrementing the persisted daily LLM spend (`BudgetDay`), and appending `AuditEvent`s. v1 of the architecture said the api never holds a write identity for `ops` and has "no port" on the worker, while `03` §10 routed these writes through a worker-owned internal `enqueue` call and ADR 0012 had the api "create tasks" without an identity. The threat model found the gap (TRD-SR-049); B13 resolved it with a fifth ACL user. The documents then disagreed, and agents are told contracts are read-only.

## Decision

- ACL user `kb_ops`: keys `~ops`; commands `+PING +CLIENT|SETINFO +INFO +GRAPH.QUERY +GRAPH.RO_QUERY` (ADR 0002). Held by `api` only.
- The api writes exactly four labels, through four fixed templates in `app/ops_writes/`: `Task` (create only, `status = 'queued'`, kinds `sync_incremental` and `verify_finding`), `ActionDraft` (create; `status` compare-and-set `drafted → confirmed → posted|failed`), `BudgetDay` (increment), `AuditEvent` (append). Template parameters come from validated request data, never from model text other than the validated draft title and body.
- **Boundary**: `app/ops_writes/` is the only module that imports the `kb_ops` client; `app/agent/` and `app/tools/` cannot import it (import-graph test); a registry test asserts the planner's tool registry contains no `kb_ops` caller; draft persistence happens in the action service after answer validation, not inside the tool.
- **The guarantee for `ops`, stated plainly**: it is the ACL key scope (`~ops` only, so `kep` and `mem:*` are unreachable) plus four fixed templates plus the import boundary. It is **not** `GRAPH.RO_QUERY`; the three-layer read-only guarantee of ADR 0005 applies to every LLM-callable tool and every other graph.
- The worker remains the only writer of every other `ops` label; the freshness agent inside `worker` writes its own task claims and handoffs as `kb_writer` (ADR 0024). The worker's internal enqueue listener of v1 `03` §10 is dropped.

## Alternatives considered

- The `03` §10 design: a worker-owned internal enqueue service with its own token, extended with `transition` and `spend` calls. One more internal service and secret for the same four writes, with the same new labels.
- Granting `kb_memory` the `~ops` pattern: mixes two unrelated scopes in one identity.

## Consequences

- ACL tests: `kb_ops` cannot write `kep` or `mem:*`; the four templates work under the real ACL.
- Every confirm and admin call is auditable in `ops` unless cut line L12 is applied, in which case they are only in structured logs.

## Revision 2026-10-12

New (design review R13).
