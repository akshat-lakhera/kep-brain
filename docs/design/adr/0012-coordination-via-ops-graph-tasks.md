# ADR 0012 · Coordination through Task, Handoff and lease nodes in the `ops` graph

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). The api's task creation is governed by ADR 0022. Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Yes (a broker or Redis streams are alternatives) |
| Related | `02-architecture.md` §5.2, §10.2, §10.4; `03-graph-model.md` §10; ADR 0006, ADR 0022, ADR 0024 |

## Context

T02 focus: "Shared state and handoffs between agents; High-concurrency reads and writes". The system has two LLM agents (the Q&A agent in `api`, the freshness agent inside `worker`) and four jobs in `worker` (ingest, derive/analytics, detect, eval). FalkorDB executes every write query atomically and serialises writes per graph, while reads run concurrently (https://docs.falkordb.com/design/concurrency); that is the primitive a single-winner lease claim needs.

## Decision

- `ops` holds `Task {key, kind, status, payload_json, created_at, lease_until, attempts, finished_at?, result_json?, error?}`, `Agent {key, kind ∈ llm_agent|job, last_seen_at, version}`, and `Handoff {key, at, reason, state_json, outcome?}`, with edges `CLAIMED {at, lease_until}` (Agent → Task), `HAS_HANDOFF` (Task → Handoff), `FROM_AGENT`/`TO_AGENT` (Handoff → Agent), `PRODUCED` (Task → result node), `TRIGGERED_BY` (Task → SyncRun or Task) (`03` §10). Task kinds include `sync_incremental`, `analytics`, `eval`, `verify_finding`, `recheck_finding`.
- A claim is one write query: match the task where `status = 'queued' OR lease_until < $now`, set `status = 'claimed'`, `lease_until = $now + 300`, `attempts += 1`, create `CLAIMED`. Serialisation makes exactly one claimer win; the loser matches nothing.
- A handoff creates a `Handoff` node with the sender's state (≤ 8 KB) and re-queues the task for the receiving agent kind; the board shows the last hour of handoffs.
- **Writers**: `worker` (`kb_writer`) creates detection, sync and analytics tasks and runs jobs; `api` (`kb_ops`) creates `Task`s only in status `queued` (`sync_incremental` from "Sync now", `verify_finding` from a Q&A answer that saw an unseen contradiction) (ADR 0022); the freshness agent in `worker` claims and completes its own tasks and writes its handoffs as `kb_writer` (ADR 0024).
- The `schedule` loop polls `ops` every 5 s; the freshness agent polls for `verify_finding`/`recheck_finding` every 5 s.
- **Wording**: in the README and the UI this is "the job queue". It is coordination state, not agent memory; the shared findings are `Finding` nodes in `kep` (ADR 0024).

## Alternatives considered

- A broker (RabbitMQ, NATS) or Redis Streams: robust at scale but a second stateful system; streams on the same server would make Redis, not the graph, the coordination store.
- A relational table with `SELECT … FOR UPDATE SKIP LOCKED`: the textbook pattern and equally good at this; not used only because FalkorDB is the single store (`02` §14.2 says so plainly).
- In-process queues: no persistence, no cross-process handoff.
- LangGraph with `FalkorDBSaver`: a framework whose internals the team would have to explain.

## Consequences

- Integration test: 20 concurrent claimers, one winner. Lease expiry (300 s) bounds a crashed agent's damage; `attempts ≥ 3` marks a task failed.
- Coordination state is inspectable as graph data on the Memory page's board.

> **Superseded content (v1 of this ADR).** v1 recorded handoffs as a `HANDED_TO {at, reason}` edge and let the api create tasks without naming an identity; replaced by `Handoff` nodes and ADR 0022.

## Revision 2026-10-12

`Handoff` nodes per `03` §10; writers per identity; new task kinds for the freshness agent; "job queue" wording (design review R4, R7, R13).
