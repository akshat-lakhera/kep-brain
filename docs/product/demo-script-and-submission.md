# KEP Brain · Demo script and submission pack

## 0. Document control

| | |
|---|---|
| Document | `docs/product/demo-script-and-submission.md` |
| Status | v0.1 draft for team sign-off (H-Demo owns, H-Lead approves). Pre-kickoff note only: Rule 8 allows notes before 2026-10-15 00:01 IST; no code, scripts or manifests. |
| Date | 2026-10-12 (IST) |
| Upstream | `PRD.md` (PRD-G/FR/US ids), `project-charter.md` (CHR-*), `docs/design/05-ui-brief.md` §4, §8; `04-eval-set.md` §5, §8; `03-graph-model.md` §12-14; ADR 0004, 0005, 0009, 0011, 0012, 0014, 0021; `FABLE_CONTEXT.md` §1, §2, §4 |
| Parts | A storyboard and recording checklist; B README judge path, "Why a graph", FalkorDB depth table; C submission-form drafts; D readiness checklist |
| IDs defined here | `DMO-SEG-nn` storyboard segments, `DMO-REC-nn` recording checks, `DMO-JP-nn` judge-path steps, `DMO-WG-nn` "Why a graph" sections, `DMO-FD-nn` depth-table rows, `DMO-FM-nn` form answers, `DMO-RDY-nn` readiness items |
| Veto-able decisions | Marked **DECISION (veto-able)**; collected in Part E and returned as open questions |
| Length cap | 450 lines |

Rules that shape everything below (FABLE_CONTEXT.md §2, PRD §2): "If the video does not show it, it does not count"; demo at most 3:00 on YouTube; live demo works without sign-up; say exactly how FalkorDB was used and give feedback; say what each member did. Judging criteria are unpublished (CHR-C-10), so this pack optimises the six-criterion template and the winner patterns, not a guess.

**No invented numbers.** Every figure below is either a ground-truth value from `04-eval-set.md` (re-verified by a human on Oct 15, HUM-03, because release v1.38 is in flight, CHR-C-09) or a placeholder written `[FILL: source]`. Placeholders are resolved from `evals/runs/<utc>/summary.json` at CP7. A placeholder left in a published file is a failed readiness item (DMO-RDY-31).

---

## Part A. The 3-minute demo video

### A.1 Questions used (real, with ground truth)

| Role in video | Id | Question (eval wording) | Ground truth to see on screen | Track | PRD |
|---|---|---|---|---|---|
| T03 hero | DEC-01 | When was KEP-1287 marked implemented, by whom, and in which PR? | commit `d47a8df46c`, 2025-12-29, `natasha41575`, `status: implementable` to `implemented`; PR #5761 "KEP-1287: Mark in-place pod resize as implemented", merged 2026-01-16; tracking issue #1287 closed 2026-01-16, milestone v1.35 | T03 | PRD-US-04, FR-026 |
| Freshness | STA-04 | What is the status of KEP-583 Coscheduling, and is that metadata current? | `kep.yaml` `status: provisional`, `last-updated: 2019-01-03`; issue #583 closed 2019-09-09, `lifecycle/rotten`; KEP-4671 and KEP-5832 declare `replaces` 583, 583 has no `superseded-by`; verdict stale | T03, feeds T01 action | PRD-US-05, FR-031, FR-033 |
| T01 multi-hop | MH-04 | If KEP-4381 were reverted, which KEPs that build on it would be affected, and which SIGs own them? | 15 KEPs: sig-node 4817, 5304, 5677; sig-scheduling 4815, 4816, 5004, 5007, 5027, 5075, 5234, 5491, 5690, 5941, 5981, 6080 | T01 | PRD-US-07, FR-055 |
| Refusal | ABS-05 | What is the status of KEP-9999? | `abstained: true`, `no_evidence`; no `9999-*` directory | T03 | PRD-US-08, FR-012 |
| Algorithm | EXP-01 / `rank_people` | Who knows most about Dynamic Resource Allocation? / `rank_people(sig-node)` | EXP-01 proxy counts `pohly` 16, `johnbelamaric` 15, `dom4ha` 13; PageRank top three for sig-node expected `dchen1107`, `mrunalp`, `derekwaynecarr` in some order (PRD-US-10, to be confirmed at CP5, not asserted in narration before it is) | T01, T03 | PRD-US-03, US-10, FR-057 |

STA-04 (KEP-583: status, and whether that metadata is current) is the README judge path's first step (DMO-JP-01) and the `/judge` first step (06 §1.3 B29). OWN-01 stays in the scored eval, off the judge path (B30). If a ground-truth value changes at HUM-03, change the question, never the expected value.

### A.2 Storyboard (target 2:55, hard cap 3:00)

**DECISION (veto-able): order and timings differ from `05-ui-brief.md` §8.** The UI brief puts Freshness before Memory and has no T01 segment other than the draft-issue action. This pack adds a T01 segment (multi-hop, algorithm, approval gate) because T01 must be demonstrated to count (PRD-G-03), moves abstention inside the hero segment, and ends on the "remove FalkorDB" argument. Alternative: keep §8 order exactly and fold MH-04 into the hero. Cost of the alternative: T01 is shown for about 10 seconds.

| Seg | Time | Screen | Narration (about 2.5 words per second) | Must be visible |
|---|---|---|---|---|
| DMO-SEG-01 | 0:00-0:12 | `/explore` index, then `/` | "Kubernetes is a company with a public org chart and public decision records. The questions are old ones: who owns this, who really knows it, why was it decided, is it still true. KEP Brain answers them from one FalkorDB graph." | URL bar with public URL, no login; SIG counts on the Explore index (three SIGs, 232 KEPs, PRD §1.2) |
| DMO-SEG-02 | 0:12-0:50 | `/` Ask. Type DEC-01 live, no paste | "I ask when KEP-1287 was marked implemented. Watch the Steps tab: the agent picks a typed tool, `trace_decision`, and FalkorDB runs a read-only parameterized Cypher query. The path draws before the prose finishes: KEP, status change, commit, pull request. The answer cites the commit and PR 5761. Every citation opens the GitHub file. FalkorDB is the only store here; the model may only use rows it returned." | Live typing; Steps tab fills with tool name, parameters, Cypher, row count, FalkorDB ms; Graph path draws with labelled edges; answer streams with `[1]` `[2]`; hover one citation; click a path node; footer "Read N nodes and M edges, K sources, Data as of ..."; no speed-up (05 §8 rule) |
| DMO-SEG-03 | 0:50-1:00 | `/` Ask, ABS-05 | "Now a KEP that does not exist. The graph returns nothing, so the agent refuses and shows what it searched." | "No evidence in the graph" block with the attempted tool calls; no claim text |
| DMO-SEG-04 | 1:00-1:20 | `/` Ask STA-04, then `/freshness?release=v1.33&sig=sig-scheduling` | "Knowledge goes stale. KEP-583's own file says provisional, last updated [VERIFY at HUM-03: 2019, read from the stored `last-updated`]. The tracker issue was closed as rotten, and two newer KEPs replace it, but nothing points back. The graph joins those three sources and flags the answer stale. Change the release and the changes table follows." | Stale badge with reason; both sources cited; release selector changed once; tiles and change table update; contradictions list contains KEP-583 |
| DMO-SEG-05 | 1:20-1:40 | `/` Ask MH-04 | "Second layer: an agent that acts. If KEP-4381 were reverted, a traversal over `see-also` edges finds 15 KEPs across two SIGs and draws the subgraph." | MH-04 answer lists 15 with SIG split and the drawn subgraph; the live load is shown, not cut (DMO-REC-05). The `algo.pageRank` person page and the MCP client stay in the README and the form (C.4), not in the video |
| DMO-SEG-09 | 1:40-1:55 | `/freshness` draft-issue dialog; GitHub issue page | "Last, the action: the agent drafts an issue from the stale KEP-583 finding. Nothing posts until I confirm, and never to kubernetes repositories." | Draft dialog with target `<team>/kep-brain-demo-actions` in mono, editable body with evidence links, the permanent note, cursor on Confirm; then the created issue on GitHub (URL bar visible, evidence links in body) |
| DMO-SEG-06 | 1:55-2:15 | `/memory`, second browser profile, Shared state tab | "Third layer: memory. Each browser gets its own FalkorDB graph. It stored this question as an episode and learned an interest in sig-scheduling. A second profile sees nothing. Agents hand work to each other through task nodes in a shared graph, so a claim is atomic." | Episodic and Semantic tabs; graph name `mem_...` in header; second profile with empty tabs; Shared-state hand-off row with lease holder and heartbeat |
| DMO-SEG-07 | 2:15-2:40 | `/eval` | "Does the graph actually help? We scored 56 questions with answer keys against four other arms: no retrieval, lexical, vector and graph-only. Here is where it wins [FILL: pooled multi-hop and temporal difference with interval]. And here is where it loses. [Read the first row of the losses table.] We publish that." | Four tiles; Chart 1; losses table sorted baseline-wins first with one row read aloud; run id and frozen date; arms not run named "not run" |
| DMO-SEG-08 | 2:40-2:55 | `/about` depth table or Rule 3 table, degraded banner, `/judge`, README top | "Remove FalkorDB and every tool, every citation, every memory and every handoff stops, because they are Cypher over the graph. Remove the model key and Explore and Freshness still work. Try it without signing up: slash judge, four clicks." | Degraded banner recorded on the local Compose stack with no key (not faked; the caption says "local"); Explore still rendering; `/judge`; README top with video link and depth table |

Time check: segments sum to 175 s. The final 5 s is slack for the title card or caption; if the cut runs over 2:58, shorten DMO-SEG-09 first (cut to the dialog and the issue page), never DMO-SEG-02 or DMO-SEG-07. SEG-05 and SEG-09 were split from one 35 s shot (about 88 words and several live navigations) so each keeps its live load.

### A.3 The "remove FalkorDB" argument (spoken in DMO-SEG-08, shown from `02-architecture.md` §14)

| Component | Without FalkorDB |
|---|---|
| `/v1/ask`, every `/v1/tools/*`, MCP server | 503 `graph_unavailable`; every tool is a Cypher template, none has a non-graph implementation |
| Evidence and paths | nothing to cite; the validator would abstain even if a model answered |
| Who-knows ranking | `algo.pageRank` and `algo.betweenness` have no replacement process |
| Decision tracing, freshness | history exists only as graph nodes and edges |
| Memory and coordination | `mem:<ULID>` graphs and `ops` task nodes are the only session and queue store |
| Ingest | worker upserts fail at the first write; a CI test fails if another database driver appears (PRD-FR-072) |

What survives: the static shell, health endpoints, the model connectivity check, the git clone. None is a product feature.

### A.4 Recording checklist

Format per `05-ui-brief.md` §8: 1920 x 1080, browser at 125% zoom, light theme, cursor visible, no music, captions burned in, real data only, URL bar visible in the first live shot.

| Id | Check | When |
|---|---|---|
| DMO-REC-01 | Ground truth in A.1 re-verified against the pinned SHA (HUM-03); video uses the final wording of the questions | Oct 15 |
| DMO-REC-02 | Rehearse the full cut twice with a stopwatch against the live deployment, not localhost; the read-through narration fits 175 s | Oct 17 evening |
| DMO-REC-03 | Clean browser profile, no extensions, no bookmarks bar, notifications off, system clock inside the hackathon window (any timestamp shown must be) | Before every take |
| DMO-REC-04 | Warm the stack: one throwaway ask per question so prompt cache and FalkorDB caches match what a judge sees; record the take with a cold-cache note only if latency is a claim | Before every take |
| DMO-REC-05 | Hero footage is not sped up (05 §8); if the answer takes longer than 38 s, retake, do not cut; p95 target is 12 s (PRD-G-04) | Take |
| DMO-REC-06 | Demo-actions repository exists, is empty of stale test issues except the one created on camera, and its URL is visible; `ACTION_REPO` is not any `kubernetes*` repo (ADR 0021) | Oct 17 |
| DMO-REC-07 | Second browser profile prepared (different memory id) before DMO-SEG-06; memory for the first profile is cleared so the episode shown was made on camera | Take |
| DMO-REC-08 | Degraded shot recorded against the **local Compose stack** with no LLM key (DMO-REC-14 allows local shots), never by pointing production at an invalid key: that would be a config deploy inside the freeze (OPS F2/F3) and would show a broken Ask to visitors. Confirm Explore, Freshness and Eval render; caption "local" | Oct 18 morning |
| DMO-REC-09 | No e-mail address, token, `.env`, terminal history or private tab visible in any frame; frame-by-frame scrub at 0.25 speed | After edit |
| DMO-REC-10 | FalkorDB's role stated aloud at least twice (CHR-SC-04): DMO-SEG-02 and DMO-SEG-08 | Edit |
| DMO-REC-11 | Captions burned in and match narration; no mockups, no stock footage | Edit |
| DMO-REC-12 | Eval numbers on screen equal the committed `summary.json` of the frozen run id; run id visible | Oct 18 12:00 (after CP7) |
| DMO-REC-13 | Upload to YouTube by 16:00; **DECISION (veto-able): visibility Public** (alternative: Unlisted; a judge link must work in a logged-out browser, test it in a private window); length at most 3:00 as YouTube displays it | Oct 18 16:00 |
| DMO-REC-14 | Fallback: if a live shot fails twice, record the same segment against the local `docker compose` stack and say "local" in the caption; do not paste a screenshot | As needed |

---

## Part B. README sections

### B.1 README top block (first screen, above everything)

1. One sentence: what it is and the three tracks (T03 master; T01, T02 layers).
2. Video link (YouTube), live link, repository link, `/judge` link.
3. The judge path (B.2), in a table.
4. Run locally: `docker compose up --build --wait` yields a loaded graph without a GitHub token (PRD-FR-051).
5. One line of AI disclosure and provenance pointing to the bottom section (C.6, PRD-FR-054).

### B.2 Judge path: "about 60 seconds, four clicks" (PRD-FR-049, PRD-OQ-06)

Base URL is `https://<LIVE_URL>` (hosting open, PRD-OQ-03). `/judge` serves these steps from the eval file; the README mirrors them and must be regenerated from `evals/questions.yaml` after HUM-03. Query strings are URL-encoded deep links that fill the composer and send.

| Id | Step | URL | Expected result | Look for |
|---|---|---|---|---|
| DMO-JP-01 | Ownership | `/?q=Which%20SIG%20owns%20KEP-1287%20(In-place%20Update%20of%20Pod%20Resources)%20and%20who%20are%20its%20approvers%3F` | `sig-node`; approvers `dchen1107`, `derekwaynecarr`, `ahg-g`, `mwielgus`, `thockin` | Path `KEP -OWNED_BY-> SIG` and approver edges; every claim has a citation; link opens `kep.yaml` |
| DMO-JP-02 | Decision | `/?q=When%20was%20KEP-1287%20marked%20implemented%2C%20by%20whom%2C%20and%20in%20which%20PR%3F` | 2025-12-29, `natasha41575`, commit `d47a8df46c`, PR #5761 merged 2026-01-16 | Steps tab shows `trace_decision` with its Cypher and FalkorDB time |
| DMO-JP-03 | Freshness | `/?q=What%20is%20the%20status%20of%20KEP-583%20Coscheduling%2C%20and%20is%20that%20metadata%20current%3F` | `provisional`, last updated 2019-01-03; issue closed 2019-09-09 `lifecycle/rotten`; 4671 and 5832 replace it; answer marked stale | Stale badge, three sources cited |
| DMO-JP-04 | Multi-hop | `/?q=If%20KEP-4381%20were%20reverted%2C%20which%20KEPs%20that%20build%20on%20it%20would%20be%20affected%2C%20and%20which%20SIGs%20own%20them%3F` | 15 KEPs: 3 sig-node, 12 sig-scheduling | Subgraph drawn from 4381; counts match |
| DMO-JP-05 | Refusal | `/?q=What%20is%20the%20status%20of%20KEP-9999%3F` | "No evidence in the graph"; `abstained: true`, `no_evidence` | Attempted tool calls listed; no invented status |
| DMO-JP-06 | Currency | `/freshness?release=v1.33&sig=sig-apps` | `sig-apps` KEPs that went stable in v1.33 or later: 3850, 3998, 3939, 4368, 5440 (v1.38 target) | Change table rows link to commits; sync status card with "Data as of" |
| DMO-JP-07 | Browse without the model | `/explore/kep/1287`, `/explore/person/dchen1107`, `/explore/sig/sig-node` | Facts, status history, "knows" panel naming the algorithm and counts | Works with the model key removed (degraded banner) |
| DMO-JP-08 | Proof | `/eval` | Run id, per-type results for five arms, losses table first, predictions versus outcomes | Arms not run are named; the ±8-point noise floor stated |
| DMO-JP-09 | Memory (T02) | `/memory` in two browsers | Disjoint episodes; hand-off table | Graph name differs per browser |
| DMO-JP-10 | Verify it is a graph | README "Queries and algorithms" section; `/about` depth table | Cypher templates and algorithm calls exported from the tool registry (Rule 10) | Every Steps-tab query appears in the README |

Steps DMO-JP-01 to 05 are the "four clicks" plus the refusal (PRD-OQ-06 default: keep five; word as "about 60 seconds"). Expected values are re-verified on Oct 15 and again on Oct 18 09:00.

### B.3 "Why a graph, not a vector database" outline (README section; winner pattern: Classroom Memory)

Target 60-80 lines. Every claim links to a number in `summary.json` or to a Steps-tab query. No claim without a measured arm.

| Id | Section | Content | Evidence |
|---|---|---|---|
| DMO-WG-01 | What the question needs | The four question families (owns, knows, decided, current) need joins across `kep.yaml`, OWNERS, tracker and PRs; a similarity search returns text, not the join | `04-eval-set.md` §4.1 types |
| DMO-WG-02 | Same corpus, five arms | N, L, V, G, H over the identical serialised blocks (`04` §8.1); why N and L exist; arm V reported "not run" if cut | Arm table from `summary.json` |
| DMO-WG-03 | Where the graph wins | Multi-hop and set completeness (MH-04: 15 KEPs, top-8 blocks cannot hold them), alias expansion (OWN 03, 05, 10), contradiction between sources (STA-04), aggregation (EXP-01) | Paired differences with bootstrap intervals; `[FILL]` |
| DMO-WG-04 | Where it does not | "Why" questions live in README prose and PR bodies; arm G (structure only) is pre-registered to lose to L and V on DEC-02 and DEC-03 (`04` §8.4); H adds full-text over sections for that reason; arm H is the slowest arm (pre-registered). State the actual outcome, using the row's own words if a prediction failed | Losses table; predictions-versus-outcomes block |
| DMO-WG-05 | What a graph adds beyond accuracy | Provenance (every node carries `source_url`, enforced by `MANDATORY` constraints), temporal edges (`valid_from`, `valid_to`), refusal when a traversal returns nothing, algorithms (`algo.pageRank`) for "who knows" | Constraint list, ADR 0008, ADR 0009, ADR 0014 |
| DMO-WG-06 | Cost | Extra latency and tool turns versus lexical RAG; token and dollar cost per answered question | `summary.json` latency and cost `[FILL]`; charter A2 estimate is labelled an estimate |
| DMO-WG-07 | How to check yourself | Run the five judge-path questions; open the Steps tab; run the eval command from the README on the local stack | B.2, run section |
| DMO-WG-08 | Caveats | Single run set of 56 questions, three reps, ±8-point noise floor, 21-question pooled subset ±13 points (PRD-G-08); ground truth from a pinned SHA; judge-model grading only for DEC and two STA clauses, calibrated on 16 human labels | `04` §6.3, §10 |

### B.4 FalkorDB depth table (README, `/about`, and the `/judge` compact version)

Columns "Where used" are route or tool names now; the "File or route" column is completed from the tool registry at CP4 (files do not exist before Oct 15). Priority: P0 T03, P1 T01, P2 T02 (PRD §0.1). Syntax and limits are taken from `03-graph-model.md` §12-14 and the charter CHR-SC-01. Items the design marks UNVERIFIED are checked on Oct 15 hour one (PRD-A-05); a row stays in the table only if it ran.

| Id | FalkorDB capability | Where used | Pri | Source |
|---|---|---|---|---|
| DMO-FD-01 | Range indexes on `key` (24 labels) and on secondary properties (`KEP.number`, `StatusChange.at`, `Person.pagerank`, ...) | every keyed tool lookup; `whats_changed`, `freshness`, `rank_people` ordering | P0 | `03` §12.2 |
| DMO-FD-02 | Full-text indexes (`KEP`, `Section`, `Issue`, `PullRequest`, `Comment`, `Person`, `SIG`, `FeatureGate`, `Decision`) with `db.idx.fulltext.queryNodes` | `find_entities`, `search_sections`, `thread_digest`, Explore search, arm L baseline | P0 | `03` §12.2 |
| DMO-FD-03 | Vector index `Section.embedding` (1024, cosine, HNSW) via `db.idx.vector.queryNodes` | semantic leg of hybrid `search_sections`; arm V in `eval_baseline` | P0 | `03` §12.2 |
| DMO-FD-04 | `UNIQUE` constraints on `key` for all labels | duplicates become violations, not silent double nodes | P0 | `03` §13 |
| DMO-FD-05 | `MANDATORY` node constraints (`source_url`, `observed_at`; `status`, `owning_sig`) and relationship constraints (`valid_from`, `valid_to`; `evidence_kind`, `source_url`) | a node without a public source URL cannot exist, so it cannot be uncited | P0 | `03` §13 |
| DMO-FD-06 | `MERGE` upserts on stable keys, temporal edges | idempotent re-runnable sync; "as of release" views (ADR 0008) | P0 | PRD-FR-004 |
| DMO-FD-07 | `GRAPH.RO_QUERY` with per-query `timeout` (2,000 ms) and server `TIMEOUT_MAX`, `RESULTSET_SIZE` | the only execution path for anything the model influences | P0 | ADR 0005; `02` §15 |
| DMO-FD-08 | ACL users: `kb_reader` read-only for the agent and MCP, `kb_writer` for the worker, password required, no published port | read-only agent access | P0 | PRD-FR-074 |
| DMO-FD-09 | Variable-length path matching and `algo.SPpaths` / `shortestPath` | `impact_of`, `path_between`, `person_to_decision`, evidence paths | P1 | ADR 0014 |
| DMO-FD-10 | `algo.pageRank('Person','COLLABORATED')`, fixed run id, results stored on nodes | `rank_people`, `who_knows` ordering, Explore "knows" panel | P1 | ADR 0014 |
| DMO-FD-11 | `algo.betweenness` with `samplingSize` 256 and `samplingSeed` 42 | `bridge_people` | P1 | ADR 0014 |
| DMO-FD-12 | `algo.WCC` and `algo.labelPropagation` | `community_of` (cluster inside the sig-node and sig-scheduling component) | P1 | ADR 0014 |
| DMO-FD-13 | One graph per user via graph selection, `mem:<ULID>` | per-user episodic, semantic, procedural memory (ADR 0011) | P2 | PRD-FR-064 |
| DMO-FD-14 | Single-writer serialisation of write queries for atomic claims | `coordinate` task leases in the `ops` graph; 20-claimer test yields one winner | P2 | ADR 0012 |
| DMO-FD-15 | `GRAPH.COPY` blue/green rebuild (`kep_next` to `kep`) carrying indexes and constraints | zero-downtime rebuild without a second store | P0 | `03` §13; CHR-SC-01 |
| DMO-FD-16 | AOF persistence and nightly backup with a tested restore | survives restart during judging (ADR 0017) | P0 | PRD-FR-075 |
| DMO-FD-17 | `GRAPH.EXPLAIN` / `GRAPH.PROFILE` | used to decide whether relationship indexes are needed (50 ms edge-scan threshold) | P0 | `03` §12.2 |

Seventeen rows against the charter minimum of twelve (CHR-SC-01). Drop any row whose feature was not exercised in the shipped build; the table is a claim a FalkorDB reviewer will check.

---

## Part C. Submission form drafts

The form questions are unpublished (`submission_questions null`, CHR-C ledger, re-read Oct 12). Re-read the public API and rules page on Oct 14 evening and Oct 18 09:00 (HUM-00c, PRD-OQ-11) and map these answers to the real fields. Kunal Kushwaha's guidance, followed here: detailed answers; demo at most 3 minutes on YouTube; live demo works without sign-up; exact FalkorDB usage plus feedback; what each member did. Bracketed items are filled at CP7-CP8 from committed files; nothing in brackets is guessed now.

### C.1 Project summary (DMO-FM-01; about 150 words)

> KEP Brain is a company brain for the Kubernetes project, treated as a company: SIGs are teams, KEPs are decision records, GitHub issues and PR threads are tickets and chats. It answers four questions with sources: who owns this, who actually knows it, why was it decided and by whom, and is that still true. All knowledge for `sig-node`, `sig-scheduling` and `sig-apps` (232 KEPs, their approvals, OWNERS files, tracking issues and PRs) lives in one FalkorDB graph. An agent chooses among typed, parameterized graph tools, runs them read-only, and returns an answer where every claim carries evidence ids, the graph path that produced it, GitHub source links and a freshness stamp. When the graph holds no evidence it refuses. It is measured: 56 questions with answer keys, scored over five arms including lexical and vector RAG, with losses published first. It is not issue triage or reviewer routing.

### C.2 How FalkorDB was used (DMO-FM-02)

Lead with the Rule 3 statement, then the table in B.4 in prose form:

- FalkorDB v4.22.0 is the only datastore: four graph families (`kep`, `ops`, `mem:<ULID>`, `eval_baseline`), [FILL at CP7: node and edge counts measured on the deployed graph; no estimate is quoted, see TRD §2], no relational store, queue or cache. A CI test fails if another database driver appears.
- Every tool is a Cypher template run through `GRAPH.RO_QUERY` as an ACL user with only read rights, with a per-query timeout. No free-form text-to-Cypher in the judged path (ADR 0004).
- Indexes: range, full-text and vector, all inside FalkorDB; `UNIQUE` and `MANDATORY` constraints enforce one node per key and a public source URL on every citable node; `MERGE` makes sync idempotent.
- Algorithms as agent tools: `algo.pageRank` for "who knows", `algo.betweenness` for bridges, `algo.WCC` and `algo.labelPropagation` for communities, `algo.SPpaths` for explanation paths (ADR 0014).
- T02: one graph per user via graph selection; task and lease nodes in `ops` for agent hand-offs.
- Removal test (`02` §14): without FalkorDB there are no answers, no citations, no memory and no coordination.
- Link: README "FalkorDB depth" table, `/about`, and the Steps tab on every answer.

### C.3 Feedback on FalkorDB (DMO-FM-03)

**Rule: write only what happened to the team during the build; delete anything not experienced.** Candidate items already known from reading the docs, to confirm or discard by Oct 18, each with a concrete example:

| Candidate | Observation to confirm | Constructive ask |
|---|---|---|
| `algo.pageRank` takes one label and one relationship type | Required a materialised `COLLABORATED` projection (ADR 0014) | Multi-label or typed-projection PageRank, or a documented projection pattern |
| `algo.betweenness` default seed is time-based | Fixed `samplingSeed` needed for reproducible demo numbers | Make the default seed explicit in the docs' first example |
| Constraint creation is asynchronous and `FAILED` means "not enforced" | Worker has to poll `db.constraints()` before loading | A blocking create option or a clearer failure signal |
| Behaviour that the docs left unstated and the team had to test (secondary-label index use, repeated `CREATE INDEX`, multi-property `UNIQUE` index prerequisite) | Day-one results from Oct 15 | Document the outcome |
| v4.22.0 pin, why 6.x was left out | What blocked 6.x, if anything did | State supported client and version matrix |
| Anything good | A specific thing that saved time (for example `GRAPH.COPY` carrying constraints) | none |

If any is a real bug, file a FalkorDB GitHub issue and link it here (CHR-ST-03). Tone: specific, no marketing, no flattery.

### C.4 Why each track is genuinely satisfied (DMO-FM-04)

| Track | Focus point (exact wording, `FABLE_CONTEXT.md` §1) | Where it is shown | Proof a judge can open |
|---|---|---|---|
| T03 (master) | Knowledge from docs, tickets, and chats in one graph | KEP text and `kep.yaml`, tracking issues, PR and issue comments, one graph | Explore KEP page tables (PRD-FR-002, 037) |
| | Who owns what, and who knows what | `who_owns`, `who_approves`, `who_knows` with the proxy declared | DMO-JP-01, EXP-01 |
| | Tracing decisions back to their source | `StatusChange` and `Decision` nodes to commit, PR, actor | DMO-JP-02 |
| | Keeping knowledge current as things change | 15-minute incremental sync, temporal edges, stale badge, contradictions | DMO-JP-03, DMO-JP-06 |
| | Answers with clear sources | citations validated against returned rows; abstention | DMO-JP-05; eval citation validity |
| T01 | Multi-hop reasoning | `impact_of` to 15 KEPs across two SIGs | DMO-JP-04 |
| | Graph queries and algorithms as agent tools | PageRank, betweenness, WCC, label propagation, shortest paths as typed tools | Person page "knows" panel; README algorithms section |
| | Tool selection through MCP | own MCP server, same catalog, token auth, the number of tools actually listed at CP5 (27 before cut lines) | `docs/MCP.md` screenshot (PRD-FR-059, 060) |
| | Actions based on what the graph shows | confirmed issue in the team's demo repository, evidence block; real Kubernetes repos denylisted (ADR 0021) | Freshness dialog; the created issue |
| | Explainable results | path and subgraph on every answer | Graph path tab |
| T02 | Episodic, semantic, and procedural memory | `Episode`, `Fact`, `Procedure` in `mem:<ULID>` | `/memory` tabs |
| | Persistent conversation history | answers stored and recallable across sessions | `memory.recalled[]` (PRD-US-15) |
| | Shared state and handoffs between agents | `ops` task board with leases; atomic claim | Shared-state tab; 20-claimer test |
| | High-concurrency reads and writes | 50 users for 60 s, p50/p95/p99 stored | `/eval` load table `[FILL]` |
| | Separate memory per user or tenant | graph per browser id, "Forget everything" | two-profile test (PRD-US-14) |

State plainly in the form that T03 is the master track and T01 and T02 are layers on the same core; they share one tool catalog (PRD §8). Where a layer was cut (cut lines L5, L6, `06` §8.3), remove its rows from this table; claim only what is live.

### C.5 Team contribution structure (DMO-FM-05)

Roster is open (PRD-OQ-02): 1-4 people. One person may hold several roles. Each member writes their own paragraph; the lead only edits for length.

| Role (template, `06` §3.2) | Human responsibilities that cannot be delegated | Name | Contribution (concrete, past tense) |
|---|---|---|---|
| H-Lead | Decisions, checkpoints go/no-go, ADRs, final submission | `[name]` | `[FILL]` |
| H-Review | Review and merge of every PR, security and Rule 6 review | `[name]` | `[FILL]` |
| H-Data/Eval | Oct 15 ground-truth re-verification, 16 calibration labels, frozen run sign-off | `[name]` | `[FILL]` |
| H-Demo | Video, README judge path, form text | `[name]` | `[FILL]` |

Each paragraph names: modules or screens owned, decisions made (ADR numbers), what was verified by hand, and one thing that went wrong and how it was handled. Each member must pass the explain-back (CHR-SC-08) before the form is sent; the same statement appears on `/about` and in the README.

### C.6 AI-assistance disclosure (DMO-FM-06; Rules 11-13)

> AI was used throughout and is logged. Claude Code wrote the pre-event design notes, ADRs and product documents under `docs/`; the stack, master track, data source and template boundary were fixed by the team beforehand. During the event, AI build agents wrote code inside contracts they could not change (graph names, tool signatures, API shapes), and humans decided, reviewed and merged every pull request, re-verified the ground truth by hand, hand-labelled the judge calibration set, ran the evaluation, recorded the video and submitted. At runtime the product uses Anthropic `claude-sonnet-5-5` for answering and `claude-haiku-5-5` for extraction `[confirm against the runtime configuration]`; the model ids of the AI sessions that wrote the notes and the code are copied from the session record in `docs/AI_USAGE.md` (CHR-OQ-13), not restated here; the model may only state facts that came back from graph queries, and a deterministic validator downgrades uncited claims. `docs/AI_USAGE.md` has one row per pull request (date, area, what AI did, what humans did, how it was verified); `docs/DECISIONS.md` has one record per decision. The repository began from a generic FastAPI, Next.js and FalkorDB template with no product logic, disclosed under README "Provenance"; the history begins on or after 2026-10-15 00:01 IST. All team members can explain the graph model, queries, architecture and decisions; the explain-back session is recorded in `docs/AI_USAGE.md`.

Also in the form if asked: data statement (three public Apache-2.0 repositories, e-mails and personal details stripped, post-sync PII scan, removal-request path, `NOTICE`; ADR 0020) and "never writes to kubernetes repositories" (ADR 0021).

### C.7 Other likely fields

| Field | Draft answer |
|---|---|
| Tracks entered | T03 Company Brain (master), T01 Agents That Act on Connected Data, T02 Agent Memory and Coordination; all three named (Rule 5) |
| Repository | public GitHub URL, full history `[FILL]` |
| Live deployment | `https://<LIVE_URL>`; no sign-up; also `docker compose up --build --wait` |
| Demo video | YouTube URL, at most 3:00 |
| Graph data model | README section with diagram; `03-graph-model.md` linked |
| Queries and algorithms | README "Queries and algorithms" exported from the tool registry (Rule 10) |
| Tech stack | FalkorDB v4.22.0; FastAPI; Next.js; own MCP server; Anthropic models via adapter (ADR 0010); Caddy on one VM (ADR 0017) |
| What is next | Widen to all `sig-*` by configuration; eval as release gate; evaluate FalkorDB 6.x (CHR-SC-10 to 14) |
| Challenges | Release v1.38 moving the data under the eval; REST timeline truncation fixed with GraphQL; honest losses (pick two that actually happened) |
| Blog post side prize | Not planned (PRD-NG-06) |

---

## Part D. Day-by-day readiness checklist

Rule 10 requires every submission to include the items below. Each row maps a Rule 10 item to the checks that prove it. **Submit at least four hours before close: target 18:00 IST Oct 18, hard stop 19:59 IST (close is 23:59).**

| Rule 10 item | Proving checks |
|---|---|
| Public repo | DMO-RDY-10, 22, 28 |
| README with setup and the graph data model | DMO-RDY-11, 23, 29 |
| Cypher queries or algorithms the product depends on | DMO-RDY-12, 24 |
| Demo video | DMO-RDY-25, 30 |
| Live deployment (preferred) or complete local setup | DMO-RDY-13, 26, 31 |
| Tracks entered | DMO-RDY-33, 35 |

| Id | Day (IST) | Item | Owner | Done when |
|---|---|---|---|---|
| DMO-RDY-01 | Oct 12-13 | Roster, LLM key and spend cap, hosting decided (PRD-OQ-01 to 03) | H-Lead | recorded in charter open questions |
| DMO-RDY-02 | Oct 13 | Discord servers joined (FalkorDB, WeMakeDevs) for kickoff announcements | all | joined |
| DMO-RDY-03 | Oct 14 evening | Re-read rules page and public API for judging criteria, form questions, kickoff time (HUM-00c); update section 2 of the PRD and Part C | H-Demo | dated note in `FABLE_CONTEXT.md` §1 |
| DMO-RDY-04 | Oct 14 | VM, domain or sslip fallback, API key with cap, GitHub PAT, demo-actions repo name decided | H-Lead | credentials stored, no secrets in git |
| DMO-RDY-05 | Oct 14 23:59 | Veto window closes; this document's veto-able items accepted or overturned | all | ADR/`DECISIONS.md` rows |
| DMO-RDY-06 | Oct 15 00:01 | First commit at or after 00:01; nothing back-dated | H-Lead | `git log` check |
| DMO-RDY-07 | Oct 15 | HUM-03: ground truth re-verified at pinned SHA; update A.1 and B.2 values | H-Data/Eval | changelog entry |
| DMO-RDY-08 | Oct 15 hour 1 | UNVERIFIED FalkorDB behaviours tested (index, constraint, ACL, `algo.*`); results recorded for C.3 | H-Lead | notes file |
| DMO-RDY-09 | Oct 15 23:00 (CP2) | OWN-01 and ABS-05 pass through `/v1/ask` | H-Review | CP2 smoke |
| DMO-RDY-10 | Oct 16 21:00 (CP4) | Repository public (`gh repo edit --visibility public`), tag `v0.1-t03` | H-Lead | URL opens logged out |
| DMO-RDY-11 | Oct 16 | README skeleton: top block (B.1), judge path (B.2), data-model diagram, run section | H-Demo | rendered on GitHub |
| DMO-RDY-12 | Oct 16 | Queries-and-algorithms README section generated from the tool registry | H-Review | matches Steps tab |
| DMO-RDY-13 | Oct 16 | Live URL up over HTTPS; five judge-path steps pass from a clean browser; no sign-up | H-Demo | tested in private window |
| DMO-RDY-14 | Oct 16 | `docker compose up --build --wait` tested on a clean machine without a GitHub token | H-Review | log kept |
| DMO-RDY-15 | Oct 16 | First eval pass (arms N, L, G, H, 1 rep) served by `GET /v1/eval/latest`; draft video script re-timed to real latency | H-Data/Eval | `/eval` renders |
| DMO-RDY-16 | Oct 17 13:00 (CP5) | T01 live: MH-04, `rank_people`, MCP screenshot, one issue in demo repo, `kubernetes/enhancements` refused | H-Lead | tag `v0.2-t01` |
| DMO-RDY-17 | Oct 17 | Demo-repo issue created for recording is deleted or kept deliberately; repo contains no stray issues (DMO-REC-06) | H-Demo | repo checked |
| DMO-RDY-18 | Oct 17 22:00 (CP6) | T02 live: disjoint memories, `memory.recalled[]`, 20-claimer test, 50-user load test stored, HTTPS with HSTS, nightly backup | H-Lead | tag `v0.3-t02` |
| DMO-RDY-19 | Oct 17 evening | Video rehearsals (DMO-REC-02); full 3-rep eval started | H-Demo, H-Data/Eval | stopwatch times noted |
| DMO-RDY-20 | Oct 17 | Cut-line decisions applied; remove any claim in Parts B and C that was cut | H-Lead | tables edited |
| DMO-RDY-21 | Oct 18 09:00 | Re-read rules page and API again for late changes; check live site and uptime monitor green overnight | H-Demo | note |
| DMO-RDY-22 | Oct 18 12:00 (CP7) | Eval frozen: `evals/runs/<utc>/summary.json` committed; run id in README and `docs/EVAL.md` | H-Data/Eval | commit |
| DMO-RDY-23 | Oct 18 12:00 | README evaluation section generated from `summary.json`; "Why a graph" (B.3) written with real numbers; all `[FILL]` resolved | H-Demo | grep for `[FILL]` returns none |
| DMO-RDY-24 | Oct 18 12:00 | Restore test recorded in `docs/RUNBOOK.md` | H-Lead | entry |
| DMO-RDY-25 | Oct 18 13:00-15:30 | Record, edit, scrub (DMO-REC-09), caption | H-Demo | cut at most 3:00 |
| DMO-RDY-26 | Oct 18 | Degraded-banner shot recorded on the local Compose stack (DMO-REC-08); production untouched | H-Demo | Production Ask still works |
| DMO-RDY-27 | Oct 18 | Explain-back session (45 minutes, TEAM-WA-18), outcome in `docs/AI_USAGE.md` (CHR-SC-08) | all | row exists |
| DMO-RDY-28 | Oct 18 | `git log` check: no commit before 2026-10-15 00:01; no `.env`, key or e-mail in history (gitleaks); PII invariant scan zero on latest `SyncRun` | H-Review | CI green |
| DMO-RDY-29 | Oct 18 | Provenance, data statement, NOTICE, removal path and AI disclosure sections present in README | H-Demo | reviewed |
| DMO-RDY-30 | Oct 18 16:00 | Video public on YouTube, at most 3:00, opens logged out; link in README top | H-Demo | tested |
| DMO-RDY-31 | Oct 18 16:30 | Placeholder sweep over README, `/about`, this form text: no `[FILL]`, no `<LIVE_URL>`, no `[name]` | H-Demo | grep clean |
| DMO-RDY-32 | Oct 18 17:00 | Final clean-browser pass of B.2 on the live URL and `docker compose` on a second machine | H-Review | all ten steps pass |
| DMO-RDY-33 | Oct 18 17:30 | Form text finalised from Part C; each member read and approved their paragraph; all three tracks named | H-Lead | approvals noted |
| DMO-RDY-34 | Oct 18 17:30 | Final freeze and tag. No deploy since 12:00 (OPS F2) and none during recording (F3); merges to `main` after 12:00 are limited to S1/S2 fixes and documentation (test-plan §4.3); fixes for a failing judge-path step only after 17:30 | H-Lead | tag `v1.0-submitted` (PRD §9.0) |
| DMO-RDY-35 | Oct 18 18:00 (CP8) | **Submit the form**; save confirmation and a copy of every answer | H-Lead | confirmation saved |
| DMO-RDY-36 | Oct 18 18:00-19:59 | Fix window only for broken links or a down site; re-check live site and video link; a fix after submission means re-opening the form only if the form allows edits (unknown, check) | H-Lead | site green |
| DMO-RDY-37 | After 19:59 | No changes. Keep the deployment funded until results (PRD-G-06) | H-Lead | monitor green |

Never cut, whatever slips (CHR-GOV-05): evidence-only answers with abstention, read-only graph access, Rule 6 guarantees, `docker compose up` for a judge, the eval with its losses, the video, the README judge path, and early submission.

---

## Part E. Veto-able decisions and open questions

| Id | Decision or question | Default | Alternative |
|---|---|---|---|
| DMO-Q-01 | Storyboard order and timings (A.2) differ from `05-ui-brief.md` §8: T01 gets its own segment, abstention moves into the hero | A.2 as written | Keep §8 order; T01 shown for about 10 seconds |
| DMO-Q-02 | Hero question is DEC-01 (decision tracing), not OWN-01 | DEC-01 in the video; STA-04 first on `/judge` | OWN-01 as hero: simpler path, weaker "decision" story |
| DMO-Q-03 | Honest-loss row on screen | First row of the "where the graph lost" table from the frozen run. If H wins every row, show arm G on DEC-02 or DEC-03 (pre-registered loss) and H being the slowest arm (pre-registered), labelled as such | Show only the latency cost |
| DMO-Q-04 | YouTube visibility Public | Public | Unlisted, if the form accepts it |
| DMO-Q-05 | MCP shown in the video | No: README, `docs/MCP.md` screenshot and the form only (SEG-05 was split to keep live loads) | Add stills for about 3 seconds if the cut is under 2:55 |
| DMO-Q-06 | Judge-path wording of MH-07 in the README (PRD-US-07 simplified text) must equal the final text in `evals/questions.yaml` | Copy from the eval file after HUM-03 | Link to `/judge` only |
| DMO-Q-07 | Live URL, hosting provider and domain unknown (PRD-OQ-03); all links in B.2 use `<LIVE_URL>` | Fill at CP4 | none |
| DMO-Q-08 | Form fields unpublished; Part C is mapped to guessed fields | Re-map on Oct 14 and Oct 18 | none |
| DMO-Q-09 | Whether the form can be edited after submit | Unknown; DMO-RDY-36 assumes not | none |
| DMO-Q-10 | `rank_people(sig-node)` top-three names (PRD-US-10) are expectations, not verified | Do not name them in narration until CP5 passes | Use EXP-01 counts instead |
| DMO-Q-11 | FalkorDB feedback (C.3) is a hypothesis list; the final text depends on what happens in the build | Rewrite on Oct 18 from `docs/DECISIONS.md` and issue notes | none |
| DMO-Q-12 | Team size and names (PRD-OQ-02); C.5 is a template | 1-4 people | none |
