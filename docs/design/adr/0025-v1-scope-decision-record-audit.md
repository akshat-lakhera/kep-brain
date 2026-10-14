# ADR 0025 · v1 scope: the decision-record audit

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-12 |
| Veto-able | Yes: the tool list, the judge path, the deferred set |
| Related | `02-architecture.md` §1, §6.6, §7, §12, §14; `03-graph-model.md` §15; `04-eval-set.md`; `05-ui-brief.md` §8; ADR 0004, ADR 0021, ADR 0024 |

## Context

Organiser advice (`FABLE_CONTEXT.md` §2): "One narrow job done end to end scores better than a platform with three half-finished features"; winners did "one narrow job with a checkable outcome". The v1 design had 29 tools, 10 routes, 25+ endpoints, 5 eval arms, OpenTelemetry with Jaeger, a blue/green rebuild, a backup sidecar and a seven-segment video in which several segments got about 20 seconds; `06` R7 rated scope creep high/high.

Differentiation (`gh api repos/RAJ-A58/NodeOps/readme`, read 2026-10-12): NodeOps calls itself the repository's "Company Brain", targets Tracks 01 and 03, names Kubernetes, ranks people by "`algo.pageRank` contributor importance over merged PR file footprints" and does "dependency blast radius". `FABLE_CONTEXT.md` §3 lists blast radius as the most overused T01 theme and "why did we decide X" as a T03 cliché. KEP Brain v1 shipped PageRank "who knows", directory ownership and an "if reverted" impact tool: too close.

## Decision

- **The job, in one sentence**: KEP Brain audits the Kubernetes project's decision records: it finds where KEP metadata, tracking issues and replacement declarations disagree, shows who decided each state and the evidence for it, and drafts the fix.
- **Checkable outcome**: N verified inconsistencies over the three SIGs, hand-labelled by H-Data/Eval, with precision published for detector-only and detector + agent.
- **v1 LLM-callable tools (14)**: `find_entities`, `get_kep`, `who_approves`, `who_owns`, `trace_decision`, `status_history`, `whats_changed`, `find_contradictions`, `kep_relations`, `path_between`, `rank_people`, `draft_stale_doc_issue`, `recall_memory`, `recall_findings`. Of the other 17 intents of `03` §15, `remember` and `coordinate` are system tools and 15 are deferred by default, built only if CP5 passes early (`02` §7.3).
- **Hero**: `find_contradictions` plus decision lineage (`kep_relations` for replacement and supersession chains, `trace_decision` and `status_history` for who decided and when, `path_between` from the person to the decision). `kep_relations` is described as lineage; the "if reverted / blast radius" framing is removed; `impact_of` is deferred and, if ever built, renamed `downstream_keps`.
- **Judge path**: STA-04, DEC-07, DEC-01, MH-07, ABS-10 (`02` §6.6). Directory ownership stays out of the judge path and the video.
- **Routes (v1)**: `/`, `/audit`, `/explore/kep/{number}`, `/memory`, `/eval`, `/judge`, `/about`.
- **Video**: three beats: the problem (records that disagree); the hero, at least 90 seconds, showing a finding, its lineage path, who decided, the Cypher behind it and the draft; the honest eval loss.
- **Also deferred or simplified**: blue/green rebuild (full reload plus dump re-seed), Jaeger (no-op tracer), the backup service (host cron); the replay feature is tier 2, not v1, 8 endpoints and 3 pages that only served deferred tools, WCC and label propagation.
- **README** gets a three-row comparison table (NodeOps; a generic Slack/docs company brain; KEP Brain) with one checkable differentiator each (`02` §1.3), and calls the substitutable tools "lookups the graph also serves" (`02` §14.3).

## Alternatives considered

- Keep 29 tools and rely on cut lines as fallbacks (v1): the cut lines would be applied under pressure on D3, after the time was spent.
- The reviewer's 12-tool list without `recall_findings`: leaves T02's shared memory unreachable from MCP and from the Q&A agent's tool loop (ADR 0024).
- Lead with ownership and expertise ("who owns, who knows"): overlaps NodeOps directly.

## Consequences

- Eval questions whose tools are all deferred are reported in a separate "deferred capability" bucket (delta for `04`).
- `05` loses the Explore index, person and SIG pages for v1; Freshness becomes the Audit page.
- If everything lands early, the deferred tools come back in the order of `02` §7.3, each behind a flag, without changing the judge path.

## Revision 2026-10-12

New (design review R5, R6).
