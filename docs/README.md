# KEP Brain · documentation map

| | |
|---|---|
| Status | v0.1 index for team sign-off (H-Lead). Pre-kickoff note only (Rule 8): Markdown, no source, scripts or manifests. |
| Date | 2026-10-12 (IST) |
| Owner | H-Lead (role template, 1-4 people; see the open decisions list below) |
| Event | WeMakeDevs x FalkorDB "Graph Hacks: Context for AI Agents", 2026-10-15 00:01 IST to 2026-10-18 23:59 IST. Internal hard stop for submission: 2026-10-18 18:00 IST (CP8), absolute latest 19:59 IST. |

This index lists every Markdown file under `docs/`, says who owns it and when it must change during the event, and gives reading orders for three audiences. Design decisions live in the ADRs; this file does not restate them.

Status words: **Draft v1** (written, awaiting sign-off), **Complete** (no further pre-event work), **Accepted** (ADR, frozen except its Status line), **Living** (appended to during the event).

---

## 1. Documentation map

Paths are relative to `docs/`. "Update during Oct 15-18" names the moment a change is expected; checkpoints (CP0-CP8) come from `product/project-charter.md` section 6.

### 1.1 Top-level records

| Path | Purpose | Owner role | Status | Update during Oct 15-18 |
|---|---|---|---|---|
| `AI_USAGE.md` | Disclosure log: one row per piece of AI-assisted work (rules 11-13) | H-Review | Living | One row per PR at the time the work is done; the explain-back outcome is recorded here (CHR-CMP-04); model ids fixed once from real sessions (CHR-OQ-13) |
| `DECISIONS.md` | Event decision records (ADR-0001-0003 for the template, ADR-0004 onward from Oct 15) | H-Lead | Living | One record per event decision, in the same PR as the change it governs (CHR-GOV-02) |

### 1.2 Design (`design/`)

| Path | Purpose | Owner role | Status | Update during Oct 15-18 |
|---|---|---|---|---|
| `design/01-recon-kubernetes-data.md` | Data reconnaissance: the three SIGs, repositories, counts, REST limits, pinned SHAs | H-Data/Eval | Complete | Re-run counts on Oct 15 before any figure is published (the header says GitHub numbers move daily) |
| `design/02-architecture.md` | Production architecture: components, Rule 3 table (section 14), budgets, verification ledger, ADR index (section 18) | H-Lead | Draft v1 | Oct 14 write-back of the section 17 deltas; then change only through an ADR |
| `design/03-graph-model.md` | FalkorDB graph model v1.1: node and edge families, indexes, constraints, algorithms, tool catalog (section 15) | H-Lead (owner not stated in the file; proposed) | Draft v1.1 | Day-one FalkorDB checks on Oct 15 (section 19.2 item 1); its results are recorded in the DECISIONS log |
| `design/04-eval-set.md` | Evaluation design: 56 questions, five arms (N, L, V, G, H), graders, judge calibration, pre-registered predictions | H-Data/Eval | Complete | Oct 15 re-verification pass (E1); calibration of 16 hand labels; frozen run at CP7 (Oct 18 12:00) |
| `design/05-ui-brief.md` | UI and UX brief: information architecture, screens, states, accessibility, demo-video shot list (section 8) | H-Demo (owner not stated in the file; proposed) | Design notes only | Screen changes as the build lands; any change to the judge path goes to `product/demo-script-and-submission.md` |
| `design/06-build-plan.md` | Build plan v1.1: task DAG for build agents, checkpoints, contracts C1-C10 (section 4), human tasks, decisions B1-B24 | H-Lead | Complete (v1.1) | Contracts are read-only for build agents (CHR-GOV-03); a contract problem goes to a PR "Contract issue" and then to a human |

### 1.3 Architecture decision records (`design/adr/`)

All 21 ADRs are dated 2026-10-11 and have status **Accepted** (veto-able parts are noted in each file's Status line). Do not edit an accepted ADR except its Status (ADR 0001); a changed decision gets a new ADR. Owner role: H-Lead, except ADR 0016 (H-Review) and ADRs 0019-0020 (H-Data/Eval).

| Path | ADRs (number: title) |
|---|---|
| `design/adr/0001`-`0008` | 0001 MADR records; 0002 FalkorDB pinned `v4.22.0` with ACL; 0003 repo and process layout; 0004 parameterised tool catalog; 0005 read-only execution path; 0006 three graph families, no second store; 0007 git clone and REST ingestion; 0008 idempotent MERGE upserts, temporal edges, blue/green rebuild |
| `design/adr/0009`-`0016` | 0009 evidence-first answers and abstention; 0010 LLM provider adapter; 0011 per-user memory graphs, not Graphiti; 0012 coordination via `ops` Task/lease nodes; 0013 own MCP server; 0014 precomputed and bounded live algorithms; 0015 config, secrets, logging; 0016 test strategy and CI gates |
| `design/adr/0017`-`0021` | 0017 single-VM Compose and Caddy; 0018 web stack and UI constraints; 0019 data scope, three SIGs; 0020 personal data under Rule 6; 0021 action safety, demo repo only |

### 1.4 Engineering (`engineering/`)

| Path | Purpose | Owner role | Status | Update during Oct 15-18 |
|---|---|---|---|---|
| `engineering/TRD.md` | Technical requirements: NFR, TR, DR, SR ids; API rows; configuration (section 17 open questions) | H-Lead, H-Review | Draft v0.1 | Close TRD-OQ items on Oct 14 (budget, stale threshold); Oct 15 day-one verifications (TRD-OQ-15) |
| `engineering/engineering-standards.md` | Coding, review and commit standards, dependency freeze (ENG-74), disclosure of model ids | H-Lead | Draft v1 | Freeze dependencies Oct 17 18:00 (ENG-74); update the Co-Authored-By rule only from `AI_USAGE.md` |
| `engineering/security-threat-model.md` | Assets, trust boundaries, threats, SR candidates, LLM spend controls (section 9 open items) | H-Lead, H-Review | Draft v1 | Oct 15 pinned-version checks (item 12); spend and rate numbers set before CP4 |
| `engineering/test-plan.md` | Test cases TST-nnn, suites, gating, defect classes (section 12 open questions) | H-Review (approved by H-Lead) | Draft v0.1 | Record run results at each checkpoint; gate changes (TST-OQ-09) by Oct 16 |
| `engineering/traceability-matrix.md` | Maps PRD and charter goals to TR/SR/TST ids and to the rows of the track focus points | H-Review | Draft v0.1 | Regenerate on any change to TRD or TST; resolve AG-05 vs TRD-TR-043 before Oct 15 |
| `engineering/data-governance.md` | Data scope, Rule 6 guarantees G1-G4, retention, deletion, open questions (section 11) | H-Data/Eval | Draft v1 | Decide DG-OQ-02 before CP4; ask organisers DG-OQ-07 on Oct 15 |

### 1.5 Operations (`ops/`)

| Path | Purpose | Owner role | Status | Update during Oct 15-18 |
|---|---|---|---|---|
| `ops/deployment-and-operations.md` | Deployment, backups, restore drill, monitoring, decisions D1-D11 (section 14) | H-Lead | Draft v0.1 | Confirm D1, D2 and Q1-Q6 by Oct 14 18:00; D7 freeze at CP7; restore drill before CP6 |
| `ops/risk-register.md` | Risk register RSK-nnn with owners and mitigations | H-Lead | Draft v0.1 | Review at each checkpoint; add an entry for every cut-line trigger (CHR-GOV-04) |

### 1.6 Product (`product/`)

| Path | Purpose | Owner role | Status | Update during Oct 15-18 |
|---|---|---|---|---|
| `product/project-charter.md` | Vision, objectives, scope, success criteria, milestones, budget, constraints, governance, open questions (section 11) | H-Lead | Draft v1 | Close CHR-OQ items; re-check judging criteria on Oct 14 and Oct 18 09:00 (CHR-OQ-08) |
| `product/PRD.md` | Goals, users, functional requirements FR and user stories US, acceptance tests, open questions (section 12) | H-Lead | Draft v0.1 | Close PRD-OQ items; update section 2 if the judging criteria change |
| `product/demo-script-and-submission.md` | Demo storyboard, judge path, submission pack, veto-able items (Part E) | H-Demo (approved by H-Lead) | Draft v0.1 | Re-map form fields on Oct 14 and Oct 18 (DMO-Q-08); rewrite FalkorDB feedback on Oct 18 (DMO-Q-11); video by 16:00 Oct 18 |

### 1.7 Team (`team/`)

| Path | Purpose | Owner role | Status | Update during Oct 15-18 |
|---|---|---|---|---|
| `team/team-charter-and-raci.md` | Roles TEAM-R-nn, working agreements TEAM-WA-nn, RACI, human windows, open questions (section 10) | H-Lead | Draft v0.1 | Confirm roster and windows by Oct 14 (TEAM-OQ-01, 03); explain-back before CP8 (TEAM-WA-18) |

---

## 2. Start here

### 2.1 New teammate (reading order, about 90 minutes)

1. `product/project-charter.md`, sections 1-3 (vision, objectives, scope and non-goals). Note PRD-NG-01: issue triage and reviewer routing are out of scope.
2. `product/PRD.md`, sections 1-3 (goals and user stories) and `product/project-charter.md` section 8 (constraints CHR-C-01 to C-12).
3. `design/02-architecture.md`, sections 1-3, then section 14 (the Rule 3 table, which says how FalkorDB carries the product).
4. `design/06-build-plan.md`, sections 1.3 (decisions B1-B24) and 3.2 (roles), and the checkpoint table.
5. ADRs 0002, 0004, 0005, 0006 and 0009. These four explain the database pin, the tool catalog, the read-only path, the single store, and abstention.
6. `AI_USAGE.md` and `DECISIONS.md`: the rules you must follow in every PR.
7. Skim `design/04-eval-set.md` section 1 so you know what "losses" means in this project.

### 2.2 Judge (reading order, about 30 minutes; the live path is in the repository README)

1. The repository README, which the team publishes with the video and the live link: video, live link, judge path (CHR-SC-06). This `docs/README.md` is an internal map and is not the judge's entry point.
2. `product/project-charter.md`, section 4.1 (what "won T03" requires) and section 1 (vision).
3. `product/demo-script-and-submission.md`, the judge path and Part A (storyboard).
4. `design/04-eval-set.md`, sections 1-2 (questions and graders) and section 8.4 (pre-registered predictions), then the frozen results in `evals/runs/<utc>/summary.json` once committed.
5. ADR 0009 (evidence-first answers and abstention) and ADR 0005 (read-only path). These are the claims the judge will test.
6. `design/02-architecture.md` section 14 (the Rule 3 table with FalkorDB capabilities mapped to files) and `design/03-graph-model.md` section 15 (the tool catalog).

### 2.3 Build agent on Oct 15 (reading order; start at 00:01 IST)

1. `design/06-build-plan.md`, sections 0 and 4 (task cards, contracts C1-C10). Contracts are read-only; a conflict goes to a PR "Contract issue".
2. `design/03-graph-model.md`, sections 1-3 (conventions), 4-8 (the model), 12-14 (indexes, constraints, algorithms), and section 19.2 (day-one FalkorDB checks). Read only the sections for your task.
3. `engineering/TRD.md`, sections 17 (open questions) and the rows for your task's TRD-TR, TRD-DR and TRD-SR ids. Do not pick a default that another section overrides; check section 4 of this file (open decisions) first.
4. ADRs 0002 (FalkorDB pin and ACL), 0004 (parameterised tools, no text-to-Cypher), 0005 (read-only), 0008 (MERGE and temporal edges) and 0021 (action safety). Read only the ones your task cites.
5. `engineering/test-plan.md` section 7.12 (ids bound to test cases) and `engineering/engineering-standards.md` (commit rules: no commit before 00:01 IST, task id in each message, at least hourly).
6. Pre-existing scaffolding (`apps/`, `docker-compose.yml`, `.github/`, hooks) is template code under Rule 9. Do not describe it as event work.

---

## 3. Glossary

| Term | Meaning in this project |
|---|---|
| **KEP** | Kubernetes Enhancement Proposal: a design document for a change to Kubernetes, tracked in `kubernetes/enhancements`. Each KEP has a `kep.yaml` with owners, status and a tracking issue. |
| **SIG** | Special Interest Group: a Kubernetes working group. This project loads three: `sig-node`, `sig-scheduling`, `sig-apps` (ADR 0019). `sigs.yaml` is the org chart for all SIGs. |
| **OWNERS** | A per-directory file in a Kubernetes repository naming the approvers and reviewers allowed to merge changes there. Ingested as an ownership source; the person's login is public, names and company are controlled by the switch in CHR-OQ-10. |
| **PRR** | Production Readiness Review: the per-KEP questionnaire that gates a feature's release. Stored in `prr/` files; about 212 of them are in scope (charter section 3). |
| **FalkorDB** | A graph database that speaks the Redis protocol and queries in Cypher. It is the only datastore for this product (ADR 0006). Pinned to `v4.22.0` (ADR 0002). |
| **Cypher** | The graph query language used by FalkorDB. The product never generates free-form Cypher from an LLM; the LLM chooses a tool with parameters, and the tool holds the Cypher (ADR 0004). |
| **MCP** | Model Context Protocol: the standard by which an AI client discovers and calls tools. The product runs its own MCP server over the same tool catalog (ADR 0013). |
| **Evidence path** | The graph path (nodes and edges) that justifies a claim in an answer, returned as `paths` next to `claims[].evidence_ids` and `freshness` (ADR 0009, PRD-G-01). A claim with no evidence path does not reach the user. |
| **Abstention** | An explicit refusal to answer, with a reason from a fixed enum, when evidence is missing or contradictory (ADR 0009). Scored on the ABS questions; a false abstention counts as wrong (eval E6). |

---

## 4. Open decisions for the user

Merged and de-duplicated from the open-questions sections of all documents (charter section 11, PRD section 12, TRD section 17, architecture section 17, graph model section 19.2, eval section 12, build plan section 11.2, ops section 14, security section 9, test plan section 12, data governance section 11, engineering standards section 14, team section 10, demo Part E). Each row shows the default that applies until the team decides. Each default is veto-able; the veto window closes **2026-10-14 23:59 IST** (CHR-GOV-01). Where a default is not stated in the sources, the row says so.

**Conflicts between documents:** resolved 2026-10-12 per 06 §1.6 (ratified register).

### 4.1 Required before Oct 15 00:01 IST

| # | Decision | Default until decided | Sources | Needed by |
|---|---|---|---|---|
| 1 | LLM provider, keys and spend caps | Anthropic `claude-sonnet-5-5` answering and judge, `claude-haiku-5-5` extraction (ADR 0010). Hard cap $150 combined, split $80 prod/dev and $70 eval key (CHR-B-06). Daily USD budget and per-IP ask cap have no default in the sources; they are team numbers | CHR-OQ-01, PRD-OQ-01, TRD-OQ-01, TRD-OQ-11, TST-OQ-03, SR-020/022, OPS D4 | Oct 14 |
| 2 | Team roster, roles and who pays | 1-4 people on the H-Lead / H-Review / H-Data/Eval / H-Demo template. The payer for the VM and keys has no default | CHR-OQ-02, PRD-OQ-02, TEAM-OQ-01, TRD-OQ-02, TST-OQ-04, OPS Q1/Q4, DMO-Q-12 | Oct 14 |
| 3 | Hosting: provider, VM size, domain | Single VM, Docker Compose, Caddy (ADR 0017). Hetzner CPX21 class (US) or CPX22 (EU). VM size 8 GB class (OPS D1, departs from ADR 0017's 4 GB). Railway is plan B; Fly.io is the alternative. Domain has no default; the `sslip.io` fallback needs no decision | CHR-OQ-03, PRD-OQ-03, TRD-OQ-03/17, OPS D1/Q2, 06 section 11.2 item 3 | Oct 14 18:00 |
| 4 | Operator access and deploy path | Port 22 closed except allow-listed operator IPs; operator-run deploy, not an Actions SSH deploy (OPS D2) | OPS D2 | Oct 14 |
| 5 | Off-VM backup destination | Latest nightly copy off the VM (OPS D8). Destination is not chosen (OPS Q6); the alternatives are private object storage or a private release asset | OPS D8, Q6 | Oct 15 |
| 6 | Demo-actions repository name and bot account | `<team>/kep-brain-demo-actions`, created Oct 15. Bot GitHub account for the action PAT has no default | CHR-OQ-04, PRD-OQ-12, 06 section 11.2 items 4 and 10, SR-037 | Oct 15 (account: Oct 17 09:00) |
| 7 | Blue/green rebuild vs in-place rebuild | Blue/green, as in ADR 0008 | 02 section 17 | Oct 14 |
| 8 | SIG scope (swap `sig-apps` for `sig-auth`?) | Keep `sig-node`, `sig-scheduling`, `sig-apps` (ADR 0019) | 02 section 17 | Oct 14 |
| 9 | Planner model: `claude-sonnet-5-5` or `claude-opus-5-5` | `claude-sonnet-5-5` | 02 section 17 | Oct 14 |
| 10 | Git clone vs REST tree reads for documents | Git clone (ADR 0007) | 02 section 17 | Oct 14 |
| 11 | `ActionDraft` write path: `kb_ops` user vs worker-mediated `Task` queue | `kb_ops` as a fifth ACL user (TRD-OQ-13, SR-049). Veto reverts to the enqueue listener | 06 section 11.2 item 9, TRD-OQ-13, SR-049, traceability matrix | Oct 15 |
| 12 | Judge MCP token policy | Public read-only, rate-limited token, rotated after results (SR-006, OPS D5). Alternative: stdio only | SR-006, OPS D5 | Oct 16 |
| 13 | Confirm gating for drafted actions | Nonce bound to the drafting visitor (SR-038). Alternatives: public key, or open | SR-038 | Oct 15 |
| 14 | Edge protection | Caddy only, with api-level limits. Alternative: Cloudflare in front (SR-020) | SR-020 | Oct 14 |
| 15 | Anonymous memory id | Client ULID for P0 (ADR 0011, SR-002); server-minted in P1 if time allows. Alternative: passphrase-recoverable memory (PRD-OQ-08) | SR-002, PRD-OQ-08, DG-OQ-03 | Oct 16 |

### 4.2 Required before the first public deploy (CP4, Oct 16 21:00)

| # | Decision | Default until decided | Sources |
|---|---|---|---|
| 16 | `Person.name` and `company` stored | Keep, behind `STORE_PERSON_NAME_COMPANY=true` (ADR 0020). Organisers' permission to show public logins and org-chart names is assumed; ask on Oct 15 (DG-OQ-07) | CHR-OQ-10, 02 s17, 03 s19.2 item 4, DG-OQ-02/07, 06 OQ6 |
| 17 | P1 `kubernetes/kubernetes` tickets in or out of the event build | Decide at CP3 (Oct 16 14:00) on measured P0 load time; cut line L1 leaves them out | CHR-OQ-11, PRD-OQ-10, 03 s19.2 item 5 |
| 18 | `MAX_QUEUED_QUERIES` | 45 (SR-019). Alternative 500 with semaphore | TRD-OQ-12, SR-019 |
| 19 | Stale threshold S3 for answers | 90 days (TRD-TR-024). Alternatives: 180 days, or drop S3 | TRD-OQ-06, PRD-OQ-07, TST-OQ-08 |
| 20 | Embedding dimension and provider | 1024 (`03` s12.2), Voyage via the Anthropic path. Resolved at 1024 (06 §1.6, ratified). `text-embedding-3-small` for arm V needs an OpenAI-compatible key. Without any key, arm V is "not run" | TRD-OQ-07, 03 s19.2 item 3, 04 E10, 06 OQ2 |
| 21 | Memory retention | 14 days idle, 30 days during judging, 90-day turn cap. Alternative: 90 days idle (ADR 0011) | TRD-OQ-18, DG-OQ-05 |
| 22 | Backups: include `mem:*`; final private backup retention | Include `mem:*`, disclose 7-day lag on deletion (DG-OQ-06). Keep the final backup 7 days, then delete (OPS D11) | DG-OQ-06, OPS D11 |
| 23 | Spend breaker and rate-limit numbers | Global daily budget in env, persisted in `ops`; alerts at 50 % and 80 %. Per-IP ask cap and per-memory limit (30 asks / 10 min) are team numbers; the sources give no value for the daily budget | SR-022, TRD-OQ-11, charter A5 |
| 24 | Path length bound for `path_between` | `max_len` 6, if measured p99 fits 2,000 ms. Alternative 4 | SR-017 |
| 25 | Compose-up without a GitHub token | Ship a snapshot of Apache-2.0 files with `NOTICE`; comments never included (TRD-DR-009). Alternative: require a token | TRD-OQ-14, CHR-GOV-05 |

### 4.3 Event-window decisions (Oct 15-18)

| # | Decision | Default until decided | Sources |
|---|---|---|---|
| 26 | FalkorDB ACL mode default | Set by the day-one checks at Oct 15 02:30 | 06 OQ5, TRD-OQ-15 |
| 27 | Decision extraction (`design_choice`, `alternative_rejected`) in or out | Off (`EXTRACT_DECISIONS=false`), P1 | 03 s19.2 item 2, charter A6 |
| 28 | Edge validity for `sigs.yaml` and OWNERS from git history | If the history walk takes over 2 minutes, validity starts at first observation | 03 s19.2 item 6 |
| 29 | Judge model and cross-family judge | `claude-sonnet-5-5` judge with structured output, calibrated on 16 hand labels. Alternatives: `claude-haiku-5-5` judge, or a cross-family judge through the OpenAI-compatible adapter (needs that key) | 04 E3, 04 s12 |
| 30 | Who does judge calibration and the Oct 15 re-verification | H-Data/Eval; both count as participant contributions in `AI_USAGE.md` | 04 s12 |
| 31 | Latency targets (TRD-NFR-005, p50 of TRD-NFR-001) and availability (99 % of 5-minute pings) | Decided in the TRD, unmeasured; replace after CP2 measurement, publish a miss if missed. Alternative availability: 99.5 % or best effort | TRD-OQ-04/05, OPS-039 |
| 32 | Snapshot mode at CP7 and suppression sync | Frozen snapshot, suppression sync only. Alternative: keep the 15-minute sync | TRD-OQ-16, OPS D7 |
| 33 | Demo issue posted to the team's demo repository during testing | One issue, closed after verification. Alternative: throwaway repository, live issue shown only in the video | TST-OQ-10, DMO-Q-05 |
| 34 | Judge-path wording (MH-07) and hero question (DEC-01 vs STA-04) | Copy wording from the final eval file; DEC-01 as the video hero, STA-04 first on `/judge` | DMO-Q-01/02/06 |
| 35 | Honest-loss row on screen | First loss row of the frozen "where the graph lost" table; if H wins every row, show a pre-registered loss | DMO-Q-03 |
| 36 | Judge path stability (release v1.38 in flight) | Re-verify at HUM-03 on Oct 15; swap a step if upstream moved | PRD-OQ-09, CHR-C-09 |
| 37 | Priority mapping and tool-catalog status | P0 = T03, P1 = T01, P2 = T02; tool names count as requirements | PRD-OQ-04/05 |
| 38 | Results date and judging window | Unpublished; funding assumed through 2026-11-15. Re-check Oct 14 evening and Oct 18 09:00 | CHR-OQ-08, PRD-OQ-11, OPS Q5 |
| 39 | Blog-post side prize | Only after CP8; never before the submission | 06 OQ7, PRD-NG-06 |
| 40 | Commits by agents under the human's identity | Yes (ENG-12). Alternative: bot identity per agent | ENG-12 |
| 41 | Dependency freeze time | Oct 17 18:00 IST (ENG-74). Alternative: 12:00 | ENG-74 |
| 42 | Explain-back format | Two areas per person, plus a delayed second reading. Alternative: recorded session | TEAM-OQ-04, CHR-SC-08 |
| 43 | Rule 9 FAQ wording (quote not found on the rules page) | Reword `README.md` and `DECISIONS.md` ADR-0001 to the verified text; ask organisers on Discord and record the answer | CHR-OQ-05, CHR-CMP-01 |
| 44 | Model names in `AI_USAGE.md` | Fix once from the actual session records; other documents cite that record | CHR-OQ-13, engineering standards section 14 item 5 |
