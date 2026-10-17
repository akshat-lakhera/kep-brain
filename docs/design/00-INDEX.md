# 00 · KEP Brain — Executive summary and index of the design notes

| | |
|---|---|
| Status | Index, written 2026-10-12 (IST) from a read of every file in `docs/design/` (`01`–`06` and `adr/0001`–`0026`) and the pre-event planning notes (kept outside this repository). Pre-event notes only (Rule 8): no code, no manifests, no query catalog. Drafted by an AI assistant. Nothing here is a team decision until H-Lead ratifies it at HUM-00d on Oct 14 (ADR 0001, ADR 0026). |
| Event | WeMakeDevs × FalkorDB "Graph Hacks: Context for AI Agents", **2026-10-15 00:01 IST → 2026-10-18 23:59 IST**. Internal deadline: submission sent by 18:00 IST Oct 18, hard stop 19:59 (`06` header). |
| Precedence when documents disagree | `03` owns graph names and the tool catalog. `04` owns the eval. `05` owns screens and routes. `02` owns processes, ACL users and HTTP. `06` owns the schedule and scope tiers (`06` B5, §1.6). |

---

## 1. What we are building

**KEP Brain audits the Kubernetes project's decision records. It finds where KEP metadata, tracking issues and replacement declarations disagree, shows who decided each state and the evidence for it, and drafts the fix.** (`02` §1.1, `03` §0.1, ADR 0025.)

We treat Kubernetes as the "company". Its public org chart (`sigs.yaml`, `OWNERS`) and its public decision records (KEPs, tracking issues, the PRs that changed them, and the reviews and `/approve` commands on those PRs) go into one FalkorDB graph. Every answer cites graph rows and shows the path it took. When the graph holds no evidence, the agent refuses to answer.

The **checkable outcome** is a list of verified inconsistencies. On the 2026-10-12 snapshot, five predicates flag **47 distinct KEPs**. A human hand-labels every finding, and the README publishes precision twice: for the detector alone, and for the detector plus the freshness agent. The 47 is a planning number and is never quoted as a README figure (`01` D13). The demo cases are KEP-583, KEP-5832 and KEP-5978.

**What it is deliberately not:** issue triage, reviewer routing, duplicate detection or "blast radius". `RAJ-A58/NodeOps` already ships those and names Kubernetes. Directory ownership and the PageRank ranking stay out of the judge path and the video.

## 2. Master track and layers

| Track | Role | What carries it |
|---|---|---|
| **T03 Company Brain** | Master | Docs (KEP text and `kep.yaml`), tickets (tracking issues and PRs) and chats (PR and issue threads) in one graph. Ownership and approvers come from `kep.yaml`, PRR files and `OWNERS`. History and decisions are reified (`StatusChange` and `Decision` nodes). Freshness is checked by `whats_changed`, a staleness block and the audit. Every claim is cited, and the agent abstains when it has no evidence. |
| **T01 Agents that act** | Genuine layer | Parameterized tools exposed through our own MCP server, with a public read-only judge token. `algo.SPpaths` runs live (`path_between`). `algo.pageRank` and `algo.betweenness` are precomputed (`rank_people`). The paths behind each answer are rendered. One action: an issue drafted from a verified finding, posted only to the team's demo repository after a human confirms (ADR 0021). |
| **T02 Memory and coordination** | Genuine layer | Per-user `mem:<ULID>` graphs hold episodic, semantic and procedural memory, with a synchronous "Forget everything" (ADR 0011). Shared `Finding` memory is written by an LLM freshness agent (`claude-haiku-5-5`) and read by the Q&A planner (`claude-sonnet-5-5`) and by MCP clients through `recall_findings`. A job queue with leases lives in `ops` and is described as coordination, not memory. A multi-session memory eval (MEM-01..10) and a load test back the claims. |

## 3. Chosen SIGs and graph scale

- **SIGs:** `sig-node` (139 KEPs), `sig-scheduling` (58) and `sig-apps` (35): 232 KEPs plus about 5 referenced stubs (ADR 0019, `01` §7.1). Veto-able: swapping `sig-apps` for `sig-auth` changes scale by less than 10%.
- **Tickets:** P0 only by default, meaning about 575 tracking issues and about 1,600 enhancements PRs, with their threads, reviews and label/milestone history. P1 (about 2,600 `kubernetes/kubernetes` items) is an off-by-default switch. P2 is out of scope.
- **Pins:** enhancements `8659e382…` (2026-10-08), community `5c4b5f8c…`, kubernetes `fddd57cf…` (`04` source table).
- **Scale (P0):** about 30k nodes and 60k edges by `03` §16, which is canonical. `01` §7.3 estimates 21–25k nodes and 30–35k edges. With P1 the graph grows to about 60k nodes and 100–130k edges. Either size is small for FalkorDB. The binding constraints are GitHub API time and dedup correctness.
- **Model size:** 42 primary node labels and 84 relationship types across the graph families (`03` §0.4). The hero path uses 10 of the labels (`03` §0.3).

## 4. The 10 most important decisions

All of these are proposed and veto-able unless marked as fixed by the user.

1. **One narrow job: the decision-record audit.** The hero is `find_contradictions` plus decision lineage (`kep_relations`, `trace_decision`, `status_history`). Organiser advice rewards "one narrow job done end to end" (ADR 0025).
2. **FalkorDB `v4.22.0` (C engine) with password and ACL users, and a three-layer read-only path for everything an LLM influences.** The layers are reader-only code, a `kb_reader` identity holding only `+GRAPH.RO_QUERY`, and server timeouts and limits. *Fixed by the user (version and password).* The ACL user split is veto-able (ADR 0002, 0005, 0022).
3. **Parameterized tool catalog, never text-to-Cypher.** One registry feeds the agent, HTTP, MCP and the README's query section. **14 v1 LLM-callable tools** per `03` §0.2 and `06` X2 (ADR 0004 and `02` still say 13). *The principle is fixed by the user.*
4. **Evidence-first answers.** Structured claims map to evidence ids. A deterministic validator downgrades any unsupported answer to an abstention. Answer text is validated before any of it streams to the browser; the tool trace, path and citations stream live (ADR 0009).
5. **Reified, idempotent history.** `MERGE` on natural keys (KEP key = repository path, because numbers collide; Person key = lower-cased login). `StatusChange` and `Decision` nodes carry validity intervals. Soft deletes only (ADR 0008, `03` M1–M3).
6. **Ingestion without burning the API budget.** The doc layer comes from a git clone (zero API calls). Threads, reviews and timelines come from batched GraphQL, because REST was observed silently dropping label events. A dedicated bot GitHub account is used. A **published graph snapshot** lets a judge run the full graph with no GitHub token (ADR 0007, `06` B32).
7. **Two LLM agents sharing memory in the graph.** The Q&A planner (Sonnet) and the freshness agent (Haiku) share verified `Finding`s. Per-user memory graphs are hand-built, not Graphiti. No second datastore (ADR 0006, 0011, 0024, `06` B31).
8. **An honest evaluation.** 64 questions with file-checkable ground truth. Five arms: none, lexical, vector, graph-only, hybrid. The predictions are pre-registered. The CON audit precision is the headline, with a recall check on a 30-KEP blind sample. One scored run happens on a pinned `kep_eval` graph, and the README publishes where the graph loses (`04`, `06` B33).
9. **Rule 8 and Rules 11–13 compliance.** The pre-event template is archived, and the scaffold is regenerated from public generators after 00:01 IST. The first commit is notes only. Humans hand-write the schema module, the normalisation map, the questions file and the five judge-path Cypher templates. At most three AI agent lanes run at once. Every checkpoint ends with an explain-back (ADR 0023, 0026, `06` B25, B27).
10. **Deployment:** a single VM running a standalone production Compose file, with Caddy for TLS, FalkorDB not reachable from the internet, nightly host-cron backups, and a VM seeded from a dev dump. Web: Next.js 16.4.0 with Cytoscape.js and a dagre layout, so the hero path draws identically every time. *Compose, GitHub Actions and a light neutral UI are fixed by the user* (ADR 0017, 0018).

## 5. Critical path, Oct 15–18 (IST, `06` §2, §6)

| When | Checkpoint | Must be true |
|---|---|---|
| Oct 13–14 | Pre-kickoff (HUM-00a–h) | **Document reconciliation** (H-Lead, 3.5 h). **Template archived** (ADR 0023: by Oct 14 20:00; `06` HUM-00e: by 23:00, so use the earlier time). **Organisers asked in writing** (by 18:00). **19 FalkorDB checks run by hand** with `redis-cli`. **Pre-event disclosure rewritten** by a human. **VM, domain, bot account and demo repository provisioned.** **Roster, keys and budget decided.** |
| D1 Thu 08:00 | CP0 Scaffold | The notes-only first commit is dated after 00:01. Generator commits follow. CI is green. `docker compose up --wait` is healthy. |
| D1 19:00 | CP1 Graph loads | `schema apply` is idempotent. The doc layer for three SIGs loads at the pins with zero API calls. The PII scan finds 0 hits. Three read-only checks are done by hand. |
| D2 Fri 09:00 | CP2 First cited answer | OWN-01 is answered with evidence. ABS-05 abstains. The validator suite is green. |
| D2 16:00 | CP3 History and contradictions | The ticket layer is loaded. `trace_decision(1287)` returns PR #5761. `find_contradictions` lists KEP-583, KEP-5978 and KEP-5832. The snapshot round trip works. |
| **D2 22:00** | **CP4 Hard gate** | **The audit core is demoable on the deployed URL. The repository is public. The snapshot is released. Tag `v0.1-t03`.** |
| D3 Sat 15:00 | CP5 T01 | `path_between` works. The MCP server lists 13 tools. One issue is posted to the demo repository. A Kubernetes target is refused. |
| D3 22:00 | CP6 T02 | Two browser profiles show disjoint memories. A shared finding is visible through the planner and through MCP. The load test has run. **The scored eval starts (it ends at 06:00).** |
| D4 Sun 12:00 | CP7 Freeze | The eval is frozen. `AI_USAGE.md` and `DECISIONS.md` are complete. The full explain-back is held. |
| D4 18:00 | CP8 Submitted | The video is 3:00 or less, in three beats. The form is sent with every track and each member's contribution. Hard stop at 19:59. |

Every critical-path step has at least 3 hours of slack. If one slips by more than 3 hours, apply the heavy cut tier H first, then cut lines L1 onward (`06` §8.3).

## 6. Top 5 risks (`06` §8.1)

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| 1 | Scope creep turns the one job into a platform | medium / high | v1 is 14 tools and 7 routes. Tier-2 tools are added back only after CP5. CP4 is a hard gate. Cut tier H applies before L-lines. |
| 2 | FalkorDB 4.22 behaviours not yet verified (ACL key patterns, constraint latency, conditional writes) | high that one bites / medium | 19 checks are run by hand on Oct 13–14. Every check has a pre-approved fallback (`06` §4 C1). The `FALKORDB_ACL_MODE=single` fallback is a config change. |
| 3 | Rule 8, 11–13 doubt (AI-written project, pre-event code) | low / high | The template is archived and the scaffold regenerated. The first commit is labelled as notes. Core artefacts are written by humans. Every `AI_USAGE.md` row names a concrete human action. Explain-back at every checkpoint. |
| 4 | Team capacity and fatigue (about 96.5 human hours for four people; roster unknown) | high / medium | Roster profiles for 1, 2, 3 and 4 people, with their cuts applied before kickoff. Humans work the checkpoints and morning reviews, not the nights. |
| 5 | Abuse of the public surface and LLM spend | medium / high | A spend breaker that fails closed ($5 a day public, $45 per eval run). Per-IP limits. Admin and health paths are not routed publicly. The action guard has a denylist, a nonce and a compare-and-set. Kill switches by env. |

## 7. Unresolved conflicts between the documents (fix before any agent reads the folder)

**Resolved 2026-10-12.** The 19 cross-document conflicts were settled by the user ratifying every row of `06` §1.6 as proposed, and applied to `02`, `03`, `04`, `05`, the ADRs and the project docs the same day. The key values:

- **X1, shared memory:** `Finding` nodes in `kep`, written only by the worker (`kb_writer`); five ACL users; no `org_memory` graph, no `agent` service.
- **X2, v1 tools:** the 14 in `06` §1.3 B28, including `who_owns` (kept off the judge path and the video).
- **X3, judge path:** STA-04, DEC-07, DEC-01, MH-07, ABS-10.
- **X12, X13:** replay deferred to tier 2; seven routes `/`, `/audit`, `/explore/kep/{number}`, `/memory`, `/eval`, `/judge`, `/about`.
- **Template archive deadline:** Oct 14, 20:00 IST.

## 8. Open decisions for the user

1. **LLM provider and API key.** The default path needs an Anthropic key (`claude-sonnet-5-5` planner, `claude-haiku-5-5` for extraction and the freshness agent). An OpenAI-compatible key enables the fallback. A Voyage key is needed only for the tier-2 `search_sections`; eval arm V uses a local model. Also confirm the B18 budget numbers (about $87 nominal) and the $150 console spend cap. And choose the planner: Sonnet, or Opus at about twice the price.
2. **Team roster and roles.** Names for H-Lead, H-Review, H-Data/Eval and H-Demo, and each person's hours on Thu/Fri. These choose the roster profile in `06` §3.4. Each member may be on only one team, and the team has at most four people.
3. **Hosting target.** The default is a Hetzner CPX21-class VM (Ubuntu 24.04) with a real domain (fallback `<ip>.sslip.io`) and a plan-B VM at a second provider. Alternatives are Railway or Fly. Also needed: the bot GitHub account name and the `<team>/kep-brain-demo-actions` repository.
4. **Project name.** "KEP Brain" and the `kep-brain` repository name are working names used in every document. Confirm or rename before the README and the video are written.
5. **The template.** Archive and regenerate (the default), or keep it. Keeping it requires a written "yes" from the organisers before Oct 14 22:00 IST.
6. **The cross-document register in `06` §1.6.** Ratify or veto X1 and X3 first, then the rest.
7. **Pre-event FalkorDB checks.** Accept or veto the Rule 8 judgement that checks run by hand are research (`06` B26). Decide by Oct 13.
8. **Data and privacy switches.** Whether to store `Person.name` and `company` (default true on the live instance, never in the snapshot). Whether to publish 300-character comment excerpts in the snapshot or ship it without comment text (`01` D11 vs `06` B32).
9. **Scope switches.** Keep `sig-apps` or swap in `sig-auth`. Keep P1 tickets off or turn them on.
10. **Architecture vetoes recorded in the ADRs.** Six ACL users or `single` password mode. A bot account or a GitHub App. Deferring the blue/green rebuild. Cytoscape.js. OpenTelemetry off by default. Whether to write a blog post (only after CP8).

---

## 9. The documents

| File | Description |
|---|---|
| [`01-recon-kubernetes-data.md`](01-recon-kubernetes-data.md) | Verified data reconnaissance of `kubernetes/enhancements`, `community/sigs.yaml` and the `OWNERS` files: field census, data-quality traps, API limits and the REST-vs-GraphQL gap. Also covers the SIG choice, the graph-scale basis, five provenance chains, the Rule 6 scrub list, and the 47-KEP audit snapshot behind the narrow job. |
| [`02-architecture.md`](02-architecture.md) | Production architecture: the one job, containers and ACL identities, graph families, the question flow with the validate-then-reveal stream, the v1 tool catalog, ingestion budget, memory and coordination, the API contract, deployment, and an honest "what a relational/vector store would lose" table. Authoritative for processes, identities and HTTP. Its `org_memory`, 13-tool and judge-path values await HUM-00a. |
| [`03-graph-model.md`](03-graph-model.md) | The FalkorDB graph model, authoritative for every name: labels, relationships, keys, provenance envelopes, temporal and decision reification, the five contradiction predicates, the `ops` and `mem:*` graphs, indexes, constraints and algorithms. Also holds the 30 query intents (14 v1 tools) described in prose, and the human-ownership table for the hand-written core. |
| [`04-eval-set.md`](04-eval-set.md) | Evaluation design: 64 questions with pinned, line-cited ground truth, deterministic graders plus a calibrated judge, five arms (N/L/V/G/H) and pre-registered predictions. Also covers the companion experiments CON (audit precision, the headline), HOLD (PageRank vs future reviewers), MEM (multi-session memory) and SEL (MCP tool selection), with budget and schedule. |
| [`05-ui-brief.md`](05-ui-brief.md) | UI/UX brief for a light, neutral, console-style app: routes, colour and type tokens with contrast records, screen specs for Ask, Audit, KEP, Memory, Eval, Judge and About, accessibility, and the Cytoscape.js choice. Also covers the three-beat 3-minute video, anti-patterns, and the UI artefacts humans own. Its nine routes and in-v1 replay await HUM-00a. |
| [`06-build-plan.md`](06-build-plan.md) | Build plan from Oct 15 00:01 to Oct 18: 44 agent task cards in three lanes, 28 human tasks, the contract register (C0–C10), the critical path with slack, and nine checkpoints with smoke tests. Also covers the risk register, cut tiers, the README checklist, and the §1.6 register that settles the 19 cross-document conflicts. |
| [`adr/`](adr/) | 26 MADR-style architecture decision records, all "Proposed" until a named human ratifies them on Oct 14. Each states its context, decision, alternatives, consequences and what is veto-able. One-line index below. |

| ADR | Decision |
|---|---|
| [0001](adr/0001-record-architecture-decisions.md) | Decisions are recorded as MADR files. AI-drafted ADRs stay "Proposed" until a human ratifies them. |
| [0002](adr/0002-falkordb-v4-22-0-with-acl.md) | Pin `falkordb/falkordb:v4.22.0` (`-server` in prod). Six ACL users with `+INFO`. Server limits and the rotation procedure. |
| [0003](adr/0003-repository-and-process-layout.md) | One repository: `apps/api` (package `app`, four `python -m` entrypoints) and `apps/web`. Import-graph boundaries. |
| [0004](adr/0004-parameterized-tool-catalog.md) | Parameterized tool registry, with no text-to-Cypher in any path. Judge-path templates are written by hand. |
| [0005](adr/0005-read-only-execution-path.md) | Three-layer read-only path for LLM-influenced reads. The weaker write guarantees are named per identity. |
| [0006](adr/0006-three-graph-families-no-second-store.md) | Graph families inside FalkorDB. No second datastore. An honest Rule 3 statement. |
| [0007](adr/0007-ingestion-sources-git-clone-and-rest.md) | Git clone for docs, batched GraphQL for threads and history, REST for lists. Bot account. VM seeded from a dump. |
| [0008](adr/0008-idempotent-upserts-temporal-edges-rebuild.md) | `MERGE` on natural keys with content hashes. Reified `StatusChange` history. Full reload; blue/green deferred. |
| [0009](adr/0009-evidence-first-answers-and-abstention.md) | Structured claims to evidence ids. Deterministic validator. Abstention is first-class. Validate, then reveal. |
| [0010](adr/0010-llm-provider-adapter.md) | Provider adapter: Anthropic Sonnet 5.5 and Haiku 5.5 by default, OpenAI-compatible fallback. Spend budgets. |
| [0011](adr/0011-per-user-memory-graphs-not-graphiti.md) | Hand-built `mem:<ULID>` graphs (episodic, semantic, procedural) instead of Graphiti. Synchronous forget. |
| [0012](adr/0012-coordination-via-ops-graph-tasks.md) | `Task`, `Handoff` and lease nodes in `ops`. Atomic single-winner claims. Described as a "job queue". |
| [0013](adr/0013-own-mcp-server.md) | Own MCP server over the read-only registry (Streamable HTTP and stdio) with a public judge token. |
| [0014](adr/0014-graph-algorithms-precomputed-and-live.md) | pageRank and betweenness precomputed with a fixed seed. SPpaths live and bounded. WCC and label propagation deferred. |
| [0015](adr/0015-config-secrets-logging-tracing.md) | Env-only config with unprefixed names. structlog JSON logs. Request ids. Error taxonomy. OpenTelemetry off by default. |
| [0016](adr/0016-test-strategy-and-ci-gates.md) | Unit, integration and ACL tests against a real FalkorDB, plus contract tests, the eval harness and required CI gates. |
| [0017](adr/0017-deployment-single-vm-compose-caddy.md) | Single VM with Compose and Caddy TLS. Host-cron backups. Dev ports 6380 and 3001; 6379 and 5432 are never used. |
| [0018](adr/0018-web-stack-and-ui-constraints.md) | Next.js 16.4.0, React 19.3, Tailwind 4.3, Cytoscape.js with dagre. v1 routes. Validated reveal on Ask. |
| [0019](adr/0019-data-scope-three-sigs.md) | Scope: sig-node, sig-scheduling and sig-apps. P0 tickets only; P1 is a snapshot switch. |
| [0020](adr/0020-personal-data-handling-rule-6.md) | Rule 6: e-mails never stored, text scrubbed before hashing, comments never committed, an erasure path. |
| [0021](adr/0021-action-safety-demo-repo-only.md) | The only action is an issue drafted from a verified finding. Demo repository only, with a denylist and human confirmation. |
| [0022](adr/0022-kb-ops-identity.md) | `kb_ops`: the api's four fixed-template writes to `ops`, with that guarantee stated plainly. |
| [0023](adr/0023-pre-event-template-archive-and-regenerate.md) | Archive the pre-event template, ask the organisers, regenerate the scaffold after 00:01 IST. |
| [0024](adr/0024-shared-org-memory-and-freshness-agent.md) | Haiku freshness agent; superseded in part 2026-10-12: findings are `Finding` nodes in `kep`, written by the worker (`06` §1.6 X1, ratified). |
| [0025](adr/0025-v1-scope-decision-record-audit.md) | v1 scope is the decision-record audit. Deferred tools. Three-beat video. NodeOps comparison table. |
| [0026](adr/0026-human-ownership-and-ai-lane-cap.md) | Named human owners for the core artefacts. At most three AI lanes. Explain-back at checkpoints. |

**Notes that do not exist yet** (planned by `06` §1.4): `07-falkordb-capability-checks.md` (HUM-00f, H-Review) and `08-pre-event-disclosure.md` (HUM-00g, H-Lead). Both are human-written on Oct 13–14.
