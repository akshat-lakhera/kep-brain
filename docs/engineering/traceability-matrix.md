# KEP Brain · Traceability matrix

| | |
|---|---|
| Document | `docs/engineering/traceability-matrix.md` |
| Version / status | v0.1 draft for team sign-off (H-Review owns, H-Lead approves). Pre-kickoff note: Markdown only, no source, scripts or manifests (Rule 8). |
| Date | 2026-10-12 (IST) |
| Sources read | `FABLE_CONTEXT.md` §1, §2, §4; `project-charter.md`; `PRD.md` (all); `TRD.md` (all); `test-plan.md` (all); `security-threat-model.md` §4-§6; `06-build-plan.md` task cards (§5) and checkpoints (§6); `demo-script-and-submission.md` Part A and C.4 |
| Length cap | 400 lines |

## 0. How to read this file

- This file only links ids that exist in the sources. It defines no new requirement, test or task id. A missing link is written **GAP** with the missing thing described; no id is invented.
- The test plan now binds TRD ids to cases (test-plan §7.12, TST-OQ-01 closed 2026-10-12), but only for the ids it lists; the TRD column below still comes from the TRD's own "Realises" column and the TST column from the test plan's "Refs" column joined through the PRD-FR id, so links outside §7.12 remain **derived**. Gaps closed by the 2026-10-12 review are marked "closed" with the new case id; they are required at the checkpoint named in the test plan (TST-018 CP4/CP7, TST-019 and TST-056/057 CP3, TST-058 and TST-192 CP7, TST-144/145/193/195 CP6, TST-194 CP1).
- Pri: P0 = T03 core, P1 = T01 layer, P2 = T02 layer (PRD §0.1). "Task" is a build-plan task card id (`06-build-plan.md` §5). Demo timestamps are the storyboard segments of `demo-script-and-submission.md` A.2: SEG-01 0:00-0:12, SEG-02 0:12-0:50, SEG-03 0:50-1:00, SEG-04 1:00-1:20, SEG-05 1:20-1:40, SEG-09 1:40-1:55, SEG-06 1:55-2:15, SEG-07 2:15-2:40, SEG-08 2:40-2:55.
- Cut lines (`06` §8.3) turn a row into "N/A-cut" in reports (test plan §9); they are not gaps.

## 1. Track focus points to requirement, design, test, task and demo

Focus-point wording is quoted from `FABLE_CONTEXT.md` §1 "Tracks".

| # | Track | Focus point (quoted) | Pri | PRD-FR | TRD | TST | Build task | Demo | Flag |
|---|---|---|---|---|---|---|---|---|---|
| 1 | T03 | "Knowledge from docs, tickets, and chats in one graph" | P0 | 001, 002, 003, 029 | TR-001, 003, 008, 009; DR-011, DR-015 | 001, 006, 014, 054 | ING-01, ING-02, ING-03, GR-04 | SEG-01 (0:00-0:12, Explore counts) | Chats: FR-029 `thread_digest` is cut line L4, test N/A-cut with it |
| 2 | T03 | "Who owns what, and who knows what" | P0 | 006, 018-023, 037, 063 | TR-021, 022, 003; NFR-008 | 002, 012, 040-045, 042, 073 | GR-03a, GR-03b, GR-04, WEB-04 | OWN-01 is not in the video (A.1 note); "knows" panel not in the video (README only); README judge path DMO-JP-01 | No dedicated video segment; shown only as the person-page panel. TST-042 is tier P, run at checkpoints only |
| 3 | T03 | "Tracing decisions back to their source" | P0 | 024-028 | TR-004, 005, 009, 021; DR-015 | 013, 046, 047, 048, 049 | ING-04, GR-03b, GR-04 | SEG-02 (0:12-0:50, DEC-01) | none |
| 4 | T03 | "Keeping knowledge current as things change" | P0 | 004, 007, 008, 017, 030-035 | TR-008-013, 024; DR-021, DR-022; NFR-014, 016, 017 | 005, 008, 009, 010, 028, 044, 050-053, 075 | ING-03, ING-05, GR-03b, WEB-05 | SEG-04 (1:00-1:20, STA-04 + release selector) | GAP: no test for TRD-TR-024 boundaries (89, 90, 91 days) or for TRD-NFR-016/017; see §3 |
| 5 | T03 | "Answers with clear sources" | P0 | 003, 010-016, 036, 038 | TR-020, 030-033; DR-015, DR-024 | 020-025, 031, 071, 072, 103 | AG-02, GR-02, WEB-02 | SEG-02 and SEG-03 (0:50-1:00, ABS-05) | none |
| 6 | T01 | "Multi-hop reasoning" | P1 (FR-063 P0) | 055, 063 | TR-021, 025; SR-017 | 110, 054, 156, 203 | GR-05, GR-04 | SEG-05 (1:20-1:40, MH-04) | none |
| 7 | T01 | "Graph queries and algorithms as agent tools" | P1 | 057, 058 | TR-018, 025; SR-018 | 112, 113, 114 | ING-04, GR-05 | README only (`algo.pageRank` on the person page left the video when SEG-05 was split) | TST-112 asserts top-three only; TRD-TR-018 "same seed gives same ranks" has no test (GAP). L5 (community/bridge) is the first cut |
| 8 | T01 | "Tool selection through MCP" | P1 | 059, 060 | TR-034, 035, 036; SR-035, 036 | 065, 115, 116, 117, 169 | AG-04, HUM-05 | Not in the video (DMO-Q-05); README and `docs/MCP.md` screenshot | Weakest video coverage: may be omitted; the README screenshot (TST-117) is then the only visible proof |
| 9 | T01 | "Actions based on what the graph shows" | P1 | 061, 062 | TR-043, 054; SR-012, 037-040, 049 | 118-122 | AG-05, WEB-06, HUM-08 | SEG-09 (draft dialog, then GitHub issue) | AG-05 says the worker creates `ActionDraft` from a `Task`; TRD-TR-043 / SR-049 say `api` writes it as `kb_ops` (open question 2). TST-119 is manual, live |
| 10 | T01 | "Explainable results" | P1 (FR-015, 038 P0) | 015, 038, 056, 062 | TR-025, 032, 054 | 025, 074, 111, 123 | GR-05, WEB-03, WEB-06, AG-02 | SEG-02 (path draws before prose), SEG-05 (subgraph) | none |
| 11 | T02 | "Episodic, semantic, and procedural memory" | P2 | 065, 066, 067, 068 | TR-045-048; SR-011, 028 | 133, 134, 135, 136 | GR-06 | SEG-06 (1:55-2:15, Episodic and Semantic tabs) | No P0/P1 requirement (P2 by the PRD-OQ-04 mapping). Procedural (FR-067) is cut line L6 and is not shown in the storyboard |
| 12 | T02 | "Persistent conversation history" | P2 | 065, 068, 070 | TR-045, 048, 050 | 133, 135, 137 | GR-06, WEB-07 | SEG-06 | P2 only. Persistence across API restart is a TRD-TR-045 verification with no TST (GAP) |
| 13 | T02 | "Shared state and handoffs between agents" | P2 | 069 | TR-049, 012; NFR-011; SR-046 | 138, 139, 140, 142 | GR-07 | SEG-06 (Shared-state tab) | P2 only. TRD-NFR-011 asks for 100 repeats; TST-144 states the 100 repeats (closed) |
| 14 | T02 | "High-concurrency reads and writes" | P2 | 071 | TR-051; NFR-001, 010; SR-019 | 141, 161 | EV-03 | none in the storyboard; A.1/§8 only say "load test figures (if quoted)" | P2 only. GAP: no demo timestamp unless the figures are quoted in SEG-07 or the form |
| 15 | T02 | "Separate memory per user or tenant" | P2 | 064, 070 | TR-044, 050, 059; SR-001, 002, 003, 021 | 066, 130, 131, 132, 137, 143 | GR-06, WEB-07 | SEG-06 (second profile sees nothing) | P2 only. SR-002 (server-minted ids) and SR-003 (id masking) have no test (GAP, §4) |

Result of the flag check: all 15 focus points have at least one requirement and at least one test. Points 11-15 (all of T02) have no P0 or P1 requirement by design (PRD-OQ-04); they are P2. Point 14 has no demo timestamp. Points 4, 7, 8, 12 and 13 carry the partial-test gaps noted above.

## 2. Hackathon rules to requirements, documents and tests

The context file gives Rules 2-3 as one pair and Rules 11-13 as one group (`FABLE_CONTEXT.md` §0). No individual numbers within the group are verified, so the three rows below are labelled by obligation (a) disclose AI use, (b) explain the model, queries, architecture and decisions, (c) meaningful human contribution and verification, else "may be rejected"; the documents cite the group as "Rules 11-13".

| Rule | Evidencing requirements | Evidencing documents / artefacts | Tests | Status |
|---|---|---|---|---|
| 2-3 FalkorDB must carry the product | PRD-FR-072, 073, 074, 013; PRD-C-02; TRD-TR-014, 015, 016, 019; TRD-SR-013 | `02-architecture.md` §14 (Rule 3 "remove FalkorDB" table); ADR 0002, 0004, 0005, 0006; README depth table and Rule 3 table (DMO-FD-01..17); `/about` | TST-190 (no second store), TST-004 (indexes, constraints), TST-150 (read-only), TST-152 (templates), TST-082 (depth table >= 12 rows), TST-187 (README), TST-065 | Covered. Demo: SEG-08 (2:40-2:55) |
| 5 (tracks named; context for 10) | PRD-FR-053; PRD-C-06 | `demo-script-and-submission.md` C.4 (15 focus points), C.5 | TST-208 | Covered (manual) |
| 6 public, synthetic or own data only | PRD-FR-005, 009, 066; PRD-NG-05; PRD-C-03; TRD-TR-003, 006, 007; TRD-DR-001, 010, 012; TRD-SR-028, 047 | `data-governance.md`; ADR 0020; `NOTICE`; data statement; `/about` | TST-003 (scrub property test), TST-007 (invariant scan fails the run), TST-011 (removal), TST-015 (fixed hosts), TST-134 (no e-mail in memory), TST-170 (live graph sweep), TST-189 (`NOTICE`), TST-167 (secrets) | Covered. Partial: SR-028 re-scrub of `answer_markdown` and SR-047 UI statement have no test (see §4) |
| 8 timing (not requested; shown for completeness) | PRD-C-01; PRD-G-07; TRD-TR-071 | README "Provenance"; `git log` | TST-185 | Covered (manual + CI) |
| 10 submission contents | PRD-FR-049, 050, 051, 052, 053, 075; PRD-C-04; TRD-TR-066-069 | README (data model, Cypher export, setup), demo script Parts B and C, `docs/MCP.md` | TST-078, 180, 181, 187, 205, 207, 208, 209 | Covered; build tasks DOC-01, DOC-03, DOC-04, INF-05, WEB-05 |
| 11-13 (a) AI use disclosed | PRD-FR-054, 042; PRD-G-07 | `docs/AI_USAGE.md` (one row per PR), README "Provenance", form answer DMO-FM-06 | TST-186 (row per PR), TST-185, TST-082 (disclosure on `/about`) | Covered; tasks DOC-02, HUM-04 |
| 11-13 (b) team can explain model, queries, architecture, decisions | PRD-US-20; PRD-FR-054; PRD-C-05 | `docs/DECISIONS.md` (ADR per decision), explain-back outcome in `AI_USAGE.md` | TST-206 (45-minute explain-back) | Covered (manual only); tasks HUM-02, HUM-09 |
| 11-13 (c) not entirely AI-generated; human contribution and verification | PRD-FR-044 (human calibration, ground-truth re-verification); PRD-FR-054; PRD-A-08 | `docs/VERIFICATION.md` (HUM-03 record), judge calibration `judge.jsonl`, per-member contributions in the form (DMO-FM-05) | TST-101 (ground-truth re-verification), TST-095 (16 human labels, at least 15 of 16 agree), TST-206, TST-186 | Covered (manual); tasks HUM-03, HUM-04, HUM-06, HUM-09, HUM-10 |

## 3. PRD-FR to TRD to TST to build task

TRD column lists the technical requirements that realise the FR (TRD §4 and §4.13). TST column lists test cases that cite the FR in the test plan. "N/A-cut" means the test is skipped under the named cut line. GAP rows state what is missing.

### 3.1 Data (7.A)

| FR | Pri | TRD | TST | Task | Gap |
|---|---|---|---|---|---|
| 001 | P0 | TR-001, 003; NFR-013 | 001, 014 | ING-01, ING-02 | none |
| 002 | P0 | TR-008, 009; NFR-014 | 014 | ING-03 | Only TST-014 (tier P, checkpoint); no per-PR test of GraphQL timeline parity (TRD-TR-009 verification, DG-Q-07 lives in data-governance, not the test plan): GAP |
| 003 | P0 | TR-002, 020; DR-011, 015 | 001, 006, 055 | GR-02 | none |
| 004 | P0 | TR-013; DR-013, 022; NFR-015 | 005, 018 | ING-02, ING-05 | closed: TST-018 (rebuild equality, swap, unavailability bound) |
| 005 | P0 | TR-003, 006; DR-010 | 003, 007, 170 | ING-01, ING-04 | none |
| 006 | P0 | TR-001, 002, 022 | 002, 012 | ING-01, GR-03a | none |
| 007 | P0 | TR-011; NFR-017 | 007, 008 | ING-02, ING-05 | none for the record; the 24 h stale-badge rule (NFR-017) and the 30-minute SLO (NFR-027) are covered by TST-058 (closed) |
| 008 | P0 | TR-008, 010, 012; DR-003, 004; NFR-016 | 009, 010, 019 | ING-03, ING-05, GR-07 | closed: TST-019 (zero non-304 list calls, at most 60 s; TRD-NFR-016) |
| 009 | P0 | TR-006, 007; DR-012 | 011, 189 | DOC-05 | none |

### 3.2 Answering (7.B) and ownership (7.C)

| FR | Pri | TRD | TST | Task | Gap |
|---|---|---|---|---|---|
| 010 | P0 | TR-032, 037 | 022, 060, 061 | AG-02 | none |
| 011 | P0 | TR-030; DR-024 | 020, 021 | AG-02 | none |
| 012 | P0 | TR-030, 031 | 023, 031, 072 | AG-02 | none |
| 013 | P0 | TR-019, 020, 029, 035; SR-013 | 029, 055, 065, 150, 151, 152 | GR-02, GR-03a, AG-02 | none |
| 014 | P0 | TR-033, 037; NFR-007 | 024, 071 | AG-02 | none |
| 015 | P0 | TR-019, 032, 070 | 025 | AG-02, GR-02 | none |
| 016 | P0 | TR-026, 027, 028, 039, 042; NFR-019 | 026, 027, 080 | AG-01, AG-02 | GAP: TRD-TR-027 contract test on the recorded double including a `refusal` stop, and the OpenAI-compatible smoke test before CP6 (TRD-TR-026), have no TST |
| 017 | P0 | TR-023, 029 | 028 | AG-02, WEB-02 | none |
| 018 | P0 | TR-003, 021 | 040, 002 | GR-03a | none |
| 019 | P0 | TR-021 | 041 | GR-03a | none |
| 020 | P0 | TR-021, 018 | 042 | GR-03b | none |
| 021 | P0 | TR-021 | 043 | GR-04 | none |
| 022 | P0 | TR-021, 023 | 044 | GR-03a | none |
| 023 | P0 | TR-021 | 045 | GR-04 | none |

### 3.3 Decisions (7.D), currency (7.E), screens (7.F)

| FR | Pri | TRD | TST | Task | Gap |
|---|---|---|---|---|---|
| 024 | P0 | TR-004, 009 | 013 | ING-04 | none |
| 025 | P0 | TR-005; DR-020 | 013 | ING-04 | none (extraction off by default; L2) |
| 026 | P0 | TR-021 | 046, 047 | GR-03b | none |
| 027 | P0 | TR-021 | 048 | GR-03a, GR-04 | none |
| 028 | P0 | TR-002, 021 | 049 | GR-04 | none |
| 029 | P0 (L4) | TR-021 | 054 | GR-04 | N/A-cut if L4 |
| 030 | P0 | TR-021, 024 | 050 | GR-03a, ING-05 | none |
| 031 | P0 | TR-021 | 051 | GR-03b | none |
| 032 | P0 | TR-021 | 052, 054 | GR-03b, GR-04 | none |
| 033 | P0 | TR-024; NFR-017 | 050, 053, 056, 058 | GR-03a | closed: TST-056 (S1-S3 boundaries at 89, 90, 91 days), TST-058 (frozen snapshot mode); TST-050 follows TRD-TR-024 |
| 034 | P0 | TR-012, 053 | 075 | WEB-05 | none |
| 035 | P0 | TR-021, 023; DR-021 | 044, 057 | GR-03a | closed: TST-057 (removed approver edge closed, `as_of` before still returns it) |
| 036 | P0 | TR-052, 053, 057 | 070, 071, 083 | WEB-02 | none |
| 037 | P0 | TR-053 | 073 | WEB-04 | none |
| 038 | P0 | TR-052, 054; NFR-009 | 074 | WEB-03 | none (tier CP) |
| 039 | P0 | TR-040, 056 | 079 | WEB-01, WEB-02 | none |
| 040 | P0 | TR-039, 055; NFR-019 | 027, 080 | WEB-02 | none |
| 041 | P0 | TR-058; NFR-023, 024 | 081 | WEB-01 | Partial: TST-081 uses one 390 px viewport and axe; the browser matrix of NFR-024 is not tested |
| 042 | P0 | TR-053 | 082 | WEB-05 | none |

### 3.4 Evaluation (7.G), presentation (7.H)

| FR | Pri | TRD | TST | Task | Gap |
|---|---|---|---|---|---|
| 043 | P0 | TR-060 | 100, 101 | EV-01, HUM-03 | none |
| 044 | P0 | TR-061, 065 | 090-095, 104 | EV-01, HUM-06 | none |
| 045 | P0 | TR-062 | 098 | EV-02 | none |
| 046 | P0 | TR-063; NFR-004, 005, 006, 020 | 099, 098 | EV-02, EV-03 | TRD-NFR-020 (cost per 1,000) is measured inside the eval, no dedicated TST |
| 047 | P0 | TR-064 | 077, 102 | WEB-08 | none |
| 048 | P0 | TR-064 | 098, 103, 209 | EV-03, HUM-10 | none |
| 049 | P0 | TR-053, 066 | 078, 200-205 | WEB-05 | none |
| 050 | P0 | TR-067 | 082, 187 | DOC-01 | none |
| 051 | P0 | TR-068; NFR-025 | 180, 181 | INF-03, ING-05 | none |
| 052 | P0 | none (process-only, TRD §4.13) | 207 | DOC-03 | No TRD by design |
| 053 | P0 | none (process-only, TRD §4.13) | 208 | DOC-04, HUM-11 | No TRD by design |
| 054 | P0 | TR-071 | 185, 186, 206 | DOC-02, HUM-02, HUM-04 | none |

### 3.5 T01 (7.I) and T02 (7.J)

| FR | Pri | TRD | TST | Task | Gap |
|---|---|---|---|---|---|
| 055 | P1 | TR-025 | 110 | GR-05 | none |
| 056 | P1 | TR-025 | 111 | GR-05 | none |
| 057 | P1 | TR-018, 025; SR-018 | 112, 114 | ING-04, GR-05 | seed determinism untested (see row 7 of §1) |
| 058 | P1 (L5) | TR-018, 025 | 113 | GR-05 | N/A-cut if L5 |
| 059 | P1 | TR-034, 035; SR-035 | 065, 115, 116, 169 | AG-04 | none |
| 060 | P1 | TR-036 | 117 | AG-04, HUM-05 | manual only |
| 061 | P1 | TR-025, 043; SR-037-040 | 118, 119, 120, 121, 122 | AG-05, WEB-06 | none |
| 062 | P1 | TR-043, 054 | 123 | WEB-06 | none |
| 063 | P0 (L4) | TR-021 | 054 | GR-04 | N/A-cut if L4 |
| 064 | P2 | TR-044; SR-001 | 066, 130, 131, 132 | GR-06 | none |
| 065 | P2 | TR-045 | 133 | GR-06, AG-02 | GAP: persistence across API restart (TR-045 verification) not in a TST |
| 066 | P2 | TR-046; SR-011, 028 | 134 | GR-06 | none |
| 067 | P2 (L6) | TR-047 | 136 | GR-06 | N/A-cut if L6 |
| 068 | P2 | TR-048 | 135 | GR-06 | none |
| 069 | P2 | TR-049, 012; NFR-011 | 138, 139, 140 | GR-07 | none |
| 070 | P2 | TR-050, 059 | 076, 137 | WEB-07, GR-06 | none |
| 071 | P2 | TR-051; NFR-010 | 141 | EV-03 | none |

### 3.6 Platform (7.K)

| FR | Pri | TRD | TST | Task | Gap |
|---|---|---|---|---|---|
| 072 | P0 | TR-014; DR-016-020 | 004, 190 | GR-01, INF-04 | none |
| 073 | P0 (alg. P1, per-user P2) | TR-015, 017, 018 | 004, 112, 131 | GR-01 | none; `GRAPH.EXPLAIN` snapshot per template (TR-015 verification) has no named TST: GAP (minor) |
| 074 | P0 | TR-016; SR-015, 016 | 150, 154, 155, 168 | INF-02, INF-03 | none |
| 075 | P0 | TR-013, 017, 068, 069; NFR-018, 026 | 182, 183, 191 | INF-05, INF-06 | none |
| 076 | P0 | TR-037, 038, 041, 070 | 063, 064, 164 | INF-03, AG-03 | none |
| 077 | P0 | TR-071 | 188 (workflow lint only) | INF-04 | GAP: the CI-gate requirement is verified by the gate list in test-plan §5, not by a TST; no case checks branch protection or the required-check set |

## 4. Threat to mitigation requirement to test

Threat ids and `Required` columns from `security-threat-model.md` §5; test mapping from test-plan "Refs" (explicit) where a TST cites the THR or SR id, else marked "derived". Priority of each SR is in TRD §6.

| Threat | Cat | Mitigation requirement | Test | Gap |
|---|---|---|---|---|
| THR-001 memory id of another visitor | S, I | SR-001 (P0), SR-002 (P1, D), SR-003 (P1) | TST-131, 132, 066 | GAP: no TST for SR-002 server-minted ids (veto-able) or SR-003 masked id / `Referrer-Policy` |
| THR-002 id leaks via video or Referer | I | SR-003 | none | GAP: only a recording checklist item ("New identity", A.4); no TST |
| THR-003 forged client address / request id | S, R | SR-004 | TST-063, 160 | none |
| THR-004 token guessing or leak | S, E | SR-005, 027 | TST-115, 166, 167 | none |
| THR-005 indirect prompt injection | T, E | SR-007, 008, 009, 011 | TST-158, 083, 020 | none |
| THR-006 direct injection or misuse | T, D | SR-010, 022 | TST-030, 159, 162 | none |
| THR-007 memory poisoning | T | SR-011 | TST-134 (derived) | Partial: caps on facts, turns, playbooks have no test |
| THR-008 draft body spam to Kubernetes | T | SR-012, 038 | TST-122 | none |
| THR-009 Cypher injection | T, E | SR-013, 015, 017 | TST-150, 151, 152, 155, 156 | none |
| THR-010 full-text syntax injection | T, D | SR-014 | TST-153 | none |
| THR-011 reader reaches beyond catalog | E, I | SR-015, 016 | TST-154, 155 | none (Day-1, UNVERIFIED items) |
| THR-012 ingestion path (YAML bombs, `..`) | T, D | SR-013, 029 | TST-016, 017 | none |
| THR-013 expensive multi-hop | D | SR-017, 018, 019 | TST-156, 157, 114 | none |
| THR-014 query flooding | D | SR-019, 020 | TST-160, 161 | none |
| THR-015 memory exhaustion by minted ids | D | SR-001, 021, 048 | TST-132, 143 | GAP: SR-048 host alarms (disk, 70 % `maxmemory`) has no TST |
| THR-016 LLM cost exhaustion | D | SR-010, 020, 022, 023 | TST-162, 030, 160 | GAP: SR-023 cached judge-path answers (`cached: true`) has no TST |
| THR-017 provider outage in judging window | D | SR-023 | TST-026 (provider error envelope only) | GAP: no test of the OpenAI-compatible fallback or cached answers |
| THR-018 GitHub abuse / secondary limits | D | SR-005, 038, 045 | TST-166, 184, 122 | none |
| THR-019 host resource exhaustion | D | SR-048 | none | GAP: no TST (log rotation, disk check at CP6 is a TRD §8 line only) |
| THR-020 secrets or user text in logs | I | SR-024, 025 | TST-164, 062 | none |
| THR-021 error envelopes and docs | I | SR-025 | TST-062, 163 | none |
| THR-022 health and meta exposure | I | SR-026 | TST-163, 165 | none |
| THR-023 secrets in repo, CI, images | I | SR-027 | TST-167 | none |
| THR-024 personal data re-emerges | I | SR-028, 047 | TST-003, 007, 134, 170 | Partial: SR-028 re-scrub of `answer_markdown` and SR-047 UI statement untested |
| THR-025 SSRF via GitHub URLs | T, I | SR-029, 030 | TST-015, 171 | none |
| THR-026 web-edge SSRF and link abuse | I, T | SR-008, 031 | TST-083, 165 | none |
| THR-027 markup injection / XSS | T | SR-007, 008, 031 | TST-083, 158, 165 | none |
| THR-028 supply chain, packages | T, E | SR-032 | TST-190 (allowlist only) | GAP: `pip-audit`, `pnpm audit`, frozen installs and per-PR dependency vetting are CI gates (test-plan §5 `deps`), not TST cases |
| THR-029 supply chain, CI/CD | T, E | SR-033 | TST-188 | none |
| THR-030 supply chain, images and template | T | SR-032, 034 | TST-193 | closed: SR-034 image hygiene (digest pins, non-root, `cap_drop`) |
| THR-031 MCP endpoint exposure | S, E, D | SR-005, 006, 020, 035 | TST-115, 169, 160 | GAP: SR-006 judge-token rate limit and rotation untested (TST-166 checks admin and MCP token are distinct) |
| THR-032 reverse prompt injection via MCP | T | SR-036 | TST-116 (`untrusted_content`) | none for the flag; `docs/MCP.md` safety note is manual |
| THR-033 public confirm endpoint | E | SR-012, 037, 038 | TST-122, 119 | none |
| THR-034 wrong action target | E, T | SR-037, 039 | TST-120 | none |
| THR-035 non-idempotent action | T | SR-040 | TST-121 | none |
| THR-036 no audit trail | R | SR-041 | none | GAP: no TST for `AuditEvent` nodes |
| THR-037 DB exposure / lateral movement | E | SR-034, 042 | TST-168, 193 | closed |
| THR-038 VM SSH hygiene | E | SR-043 | none | GAP: no TST (host configuration; checklist item only if the ops document adds one) |
| THR-039 certificate or DNS failure | D | SR-044 | TST-182 | Partial: staging-CA rehearsal and `caddy_data` backup untested |
| THR-040 corpus or eval tampering | T | SR-005, 045 | TST-184, 166 | none |
| THR-041 cross-user leakage by shared state | I | SR-001, 046 | TST-142, 131 | none |
| THR-042 operational data privacy | I, R | SR-047 | TST-079 (storage keys; derived) | GAP: no check that logs hold hashed IPs only or that no third-party script loads (TRD-TR-056 "network panel test" has no TST) |

SR ids not linked to any threat row in §5: TRD-SR-049 (`kb_ops` fifth ACL user). It arises from an architecture gap (threat model §6.7), not a threat. Closed: TST-195 tests that `kb_ops` is confined to `~ops` (TST-150 and TST-155 cover `kb_reader`).

## 5. Orphans and open links

### 5.1 PRD requirements without a TRD

- PRD-FR-052 (demo video) and PRD-FR-053 (submission form): process-only by design (TRD §4.13). Tests exist: TST-207, TST-208.
- PRD-G-05 (video and form) and PRD-G-06 (uptime): G-05 is process (TRD §15); G-06 maps to NFR-018, NFR-026, TR-069 and TST-182, TST-183.
- PRD-G-08, G-09, G-10: mapped (TRD §15); tests TST-098, TST-102 (G-08), TST-103 (G-09), TST-078, TST-205 (G-10).
- No PRD-US without a requirement: US-01..US-20 each name an eval question or checkpoint; story-to-test links run through TST-040 (US-01), TST-002 (US-02), TST-042 (US-03), TST-046 and TST-048 (US-04), TST-053 (US-05), TST-052 and TST-075 (US-06), TST-110 and TST-123 (US-07), TST-023 and TST-072 (US-08), TST-027 and TST-073 (US-09), TST-112 (US-10), TST-111 (US-11), TST-115 and TST-117 (US-12), TST-118 and TST-119 (US-13), TST-130 (US-14), TST-135 and TST-137 (US-15), TST-138 and TST-140 (US-16), TST-141 (US-17), TST-078 and TST-205 (US-18), TST-180 and TST-181 (US-19), TST-206 (US-20).

### 5.2 TRD items without a TST (derived, see §0)

| TRD item | What is untested |
|---|---|
| TRD-NFR-003 | `graph_timeout` is covered by TST-157; the `budget_exhausted` (8 calls / 30 s) path is asserted only in TST-029 at config level |
| TRD-NFR-012 | Ingestion throughput (>= 1,000 nodes+edges/s): TST-014 records duration but states no threshold |
| TRD-NFR-016, TRD-NFR-017, TRD-NFR-027 | closed: TST-019 (no-change sync), TST-058 (stale-badge threshold and frozen mode), TST-008 (chip lag) |
| TRD-NFR-024 | Browser matrix beyond one 390 px viewport: GAP (partial) |
| TRD-TR-013, TRD-DR-013, TRD-NFR-015 | closed: TST-018 (rehearsal at real size at CP7) |
| TRD-TR-024 | closed: TST-056, TST-058 |
| TRD-TR-027 | Contract test with a `refusal` stop on the recorded double: GAP |
| TRD-DR-005 | Cache rebuild with token removed gives an identical graph hash: GAP |
| TRD-DR-007 | Egress test that a public viewer never triggers an upstream call: partial via TST-171 |
| TRD-DR-009 | "No whole-comment export route" route-list check and "no comment bodies in the repository" scan: GAP |
| TRD-DR-014 | Logs, traces and metrics carry no user text or parameter values: partial via TST-164 (canary) |
| TRD-DR-021 | closed: TST-057 |
| TRD-DR-023 | Soft delete on a deleted KEP directory: partial via TST-011 (removal request path only) |
| TRD-TR-056 | Network-panel test that only same-origin requests occur: GAP |
| TRD-TR-045 | Persistence across API restart: GAP |
| TRD-SR-002, 003, 006 (rate and rotation), 023, 041, 043, 048 | Untested; see §4. SR-034 (TST-193) and SR-049 (TST-195) are now covered; TRD-TR-073 by TST-192 |

### 5.3 Tests without a PRD-FR link

These cite design, threat or ADR ids only. They are not orphans in intent, but a reviewer looking for the FR will not find one in the test plan:

- TST-090, 091, 092, 093, 104 (eval harness self-tests; `04` §6.4, §6.1). TST-090 cites FR-044; 091-093 and 104 cite `04` only.
- TST-101 (PRD-C-10, HUM-03), TST-114 (TRD-SR-018), TST-143 (TRD-SR-021), TST-157 (ADR 0005), TST-171 (TRD-SR-029/030), TST-184 (TRD-SR-045), TST-188 (TRD-SR-033), TST-162 and TST-164 to TST-169 (security requirements).
- Unassigned TST number ranges in the catalogue (059, 084-089, 105-109, 124-129, 146-149, 172-179, 196-199, 210-229) hold no cases; none are referenced here.

### 5.4 Build-plan and document links to confirm

- Build tasks that realise no PRD-FR directly: INF-01 (repository start, serves PRD-C-01 and PRD-G-07), HUM-00a..d (pre-kickoff documentation), HUM-01, HUM-07 (visibility flip, serves TST-167).
- AG-05 versus TRD-TR-043/SR-049: different write paths for `ActionDraft` (worker via `Task` versus `api` as `kb_ops`). Decide before Oct 15 (TRD-OQ-13 is the matching open question).
- Embedding dimension: resolved 2026-10-12 at 1024, cosine (06 §1.6, ratified register; B6).
- Demo script C.4 claims T01 "Tool selection through MCP" at "at least 19 tools"; TRD-TR-034 lists 27 MCP tools before cut lines (1-26 plus `get_graph_schema`) and TST-065 and TST-115 now record the count instead of asserting 19; the form text states the number actually listed at CP5.
