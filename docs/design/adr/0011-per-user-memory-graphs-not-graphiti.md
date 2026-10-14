# ADR 0011 · Hand-built per-user memory graphs instead of Graphiti

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Yes (Graphiti or Cognee are the obvious alternatives) |
| Related | `02-architecture.md` §5.3, §10.3, §10.5; `03-graph-model.md` §11; ADR 0002, ADR 0006, ADR 0024 |

## Context

T02 focus: "Episodic, semantic, and procedural memory; Persistent conversation history; Separate memory per user or tenant". Graphiti (`graphiti-core` 0.30.2) supports FalkorDB with one `graph_name` per user, but the prep audit found ~69 open GitHub issues mentioning FalkorDB, and it needs its own LLM extraction. Our per-user needs are narrow: store episodes, learn a few facts about the user's interests, and remember which tool sequences worked. Shared, cross-agent memory is a separate graph (ADR 0024).

## Decision

- Per-user memory is the `03-graph-model.md` §11 model in graph `mem:<ULID>`: `User`, `Session`, `Episode` (episodic memory and persistent conversation history; keyed by `request_id`; stores the full validated answer), `Fact` (semantic), `Procedure` (procedural), `EntityRef` (pointer into `kep` by `label|key`).
- Identity: the browser generates the ULID, keeps it in `localStorage`, shows it, and sends it as `X-Kep-Memory-Id`; the api validates it with a full match and selects `mem:<ULID>`. No cookie, no account; the id is a random key to non-personal memory.
- Writes in `api` after the validated answer, as `kb_memory`: one atomic `remember` per answer (episode, `NEXT`, entity refs, facts extracted by `claude-haiku-5-5` with `support_count`, the procedure for the question kind; thumbs-up increments `success_count`). Lazy schema on the first write: range indexes and `UNIQUE` constraints on `key` (`kb_memory` holds `+GRAPH.CONSTRAINT`, ADR 0002).
- Reads before planning: up to 5 recent episodes, up to 20 facts, the top 3 procedures for the classified question kind; injected as context with an explicit note that memory is not evidence (ADR 0009).
- **Forget**: `DELETE /v1/memory/me` runs `GRAPH.DELETE mem:<ULID>` synchronously as `kb_memory` (`+GRAPH.DELETE`, confined to `~mem:*`). **Retention**: `memory-gc` in the worker deletes episodes older than 90 days and graphs idle that long.
- Measured, not asserted: the eval's `MEM` items run two-session scripts with and without recall and report accuracy and input tokens (`02` §10.5).

## Alternatives considered

- Graphiti: bitemporal episodes and extraction out of the box; rejected for stability risk under a four-day deadline, an extra LLM dependency we cannot control, and because every node in the memory model must be explainable by the team.
- Cognee or mem0: similar trade-offs, with their own ontologies.
- Erasure through a worker task as `kb_writer`: no extra grants, but "Forget everything" becomes asynchronous; rejected (ADR 0002).

## Consequences

- Memory is explainable in two sentences and renders on one page.
- Per-user memory is honestly substitutable by a relational schema per tenant (`02` §14.2); its value here is isolation by key and one-command erasure, and the measured effect on follow-up questions.

> **Superseded content (v1 of this ADR).** v1 named the episodic label `Turn` and the procedural label `Playbook`, and its erasure ran as a user without the delete grant; replaced by `Episode`, `Procedure` and the grants above (`03` §17).

## Revision 2026-10-12

Names aligned with `03` §11; erasure and lazy constraints made possible by the `kb_memory` grants; memory eval added; shared memory moved to ADR 0024 (design review R4, R7, R8, R10).
