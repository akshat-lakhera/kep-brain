# ADR 0024 · Shared findings in `kep` and the freshness agent

Amended 2026-10-12 per 06 §1.6 (ratified register).

Status: superseded in part (2026-10-12) — findings live in `kep`, written by the worker; this was this ADR's own listed fallback.

| | |
|---|---|
| Status | Proposed (2026-10-12). Names are proposals for `03-graph-model.md` (HUM-00a). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-12 |
| Veto-able | Yes: separate graph vs `Finding` in `kep`; separate `agent` service vs inside `worker` |
| Related | `02-architecture.md` §4.4, §5.4, §10; ADR 0002, ADR 0005, ADR 0009, ADR 0011, ADR 0012, ADR 0021 |

## Context

T02 brief: "Build agents that remember across sessions and share state with each other. Memory should persist, update over time, and be available to every agent that needs it." The 2026-10-12 review found that v1 had one LLM agent (the planner); the other "agents" were cron roles; per-user memory was read only by the planner and not reachable over MCP; and the task queue was being presented as shared memory. The product's job (`02` §1) is an audit of the project's decision records, and its checkable outcome is a list of verified inconsistencies. Verifying candidates and keeping that list current is a natural second agent, and the list itself is natural shared memory.

## Decision

- **Findings in graph `kep`** (shared across users and agents; written only by the worker as `kb_writer`): `Finding` (key `fd:<kind>:<KEP key>:<evidence hash>`; `kind`, `kep_key`, `status ∈ open|resolved|rejected|superseded`, `severity`, `summary`, both sides, `evidence_keys`, `detector_run_id`, timestamps, `verifier_model`, `support_count`), `FindingNote` (agent notes: `verified`, `rejected`, `rechecked`, `surfaced`, `drafted`), `Subject` (`label|key` of a `kep` entity); edges `HAS_NOTE`, `ABOUT`, `CITES`, `SUPERSEDES`.
- **Freshness agent** (`claude-haiku-5-5`) run inside the `worker` process, holding `kb_reader` (tools over `kep`); worker code writes its results as `kb_writer`. It claims `verify_finding` and `recheck_finding` tasks, re-runs `find_contradictions` for the KEP, gathers context with `status_history`, `kep_relations`, `trace_decision` and `who_approves`, and returns a structured verdict (holds or not, severity, newer side, summary, evidence ids). The deterministic validator (ADR 0009) checks the evidence ids; code writes the result with fixed templates (`record_finding`). Budget: `FINDINGS_AGENT_DAILY_USD` (1.00).
- **Producers of work**: the worker's `detect` job enqueues a `verify_finding` per new candidate after each sync, and a `recheck_finding` per open finding; the Q&A agent's post-processing enqueues `verify_finding` (through `kb_ops`) when its own `find_contradictions` rows include a candidate with no finding.
- **Consumers**: the Q&A agent's `recall_findings` tool; the MCP server's `recall_findings`; the Audit page; the freshness block of every answer (`open_findings[]`); `draft_stale_doc_issue` (ADR 0021). Findings are context, never evidence: their `evidence_keys` are resolved in `kep` and those rows are cited.
- **Handoffs**: on completion the agent writes a `Handoff {to: qa, reason: "finding available"}`; the board shows agents, open tasks and the last hour of handoffs.
- **Evaluation**: audit precision is reported for detector-only and for detector + agent on human labels (all findings if N ≤ 80, else a seeded 80); two `MEM` items measure the Q&A agent with and without `recall_findings`.

## Alternatives considered

- **Separate `org_memory` graph** (v1 of this ADR): rejected by the ratified register; findings are `Finding` nodes in `kep`, written only by the worker.
- **Freshness agent in its own `agent` service** (v1 of this ADR): removed by the ratified register; see the status line above.
- **Per-user memory read by system agents**: breaks "Separate memory per user or tenant"; the shared scope is the `Finding` nodes in `kep`.
- **Calling the task queue shared memory** (v1 wording): it is coordination state; the README calls it the job queue.

## Consequences

- T02's "shared state and handoffs between agents" is literal: a finding verified by the freshness agent changes what the Q&A agent tells a different user later, and the MCP client sees it too.
- `Finding` nodes are honestly substitutable by a relational table (`02` §14.2); its value is shared state between agents, measured by the precision and memory evals, not traversal.
- No extra Compose service or ACL user (five users in total, ADR 0002); the grants stay tested (ADR 0016).

## Revision 2026-10-12

New (design review R4).
