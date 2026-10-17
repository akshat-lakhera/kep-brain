# KEP Brain · Team charter and RACI

## 0. Document control

| | |
|---|---|
| Document | `docs/team/team-charter-and-raci.md` |
| Version / status | v0.1 draft for team sign-off; pre-kickoff note (Rule 8 allows notes and plans before 2026-10-15 00:01 IST). No code, scripts or manifests. |
| Date | 2026-10-12 (IST) |
| Owner | H-Lead (CHR-GOV-01) |
| Upstream | `docs/product/project-charter.md` (CHR-ST-01, CHR-GOV-01..08, CHR-CMP-03/04), `docs/product/PRD.md` (PRD-C-05, PRD-C-06, PRD-A-08, PRD-US-20, PRD-FR-053, PRD-FR-054), `docs/design/06-build-plan.md` §2.1, §3.2, §5.7, §5.8, §6, §7 |
| Length cap | 300 lines |
| Ids defined here | `TEAM-R-nn` roles, `TEAM-WA-nn` working agreements, `TEAM-OQ-nn` open questions. Other prefixes are cited, not redefined. |

Decision marking. Anything the sources leave open is **DECISION (veto-able)** with its alternative and is listed in section 10. Defaults for things the user has not decided: team of 1-4 people with roles as a template (PRD-OQ-02), LLM provider Anthropic (PRD-OQ-01), hosting single VM with Docker Compose and Caddy (ADR 0017, PRD-OQ-03).

Purpose. Rules 11-13 (the planning notes §0) allow AI assistance but require disclosure and a team that can explain "the graph model, the queries, the project architecture, and the technical decisions behind them"; entirely AI-generated work "may be rejected". About 30 human-hours exist across four days (CHR-C-11). This document says who holds which hat, who signs what, and how the human contribution is produced and recorded rather than reconstructed on Oct 18.

---

## 1. Operating principle: agents propose, humans decide, review, run

| Verb | Who | Examples |
|---|---|---|
| Propose | AI build agents (lanes A1-A6, `06` §3.3) | Code in a worktree and PR, drafts of README prose, a contract-issue note |
| Decide | Humans only | Every reconciliation decision B1-B12, scope cuts, a contract change, provider, hosting, the judge path |
| Review | Humans only | Each PR (HUM-04), each checkpoint smoke test (§6 of the build plan) |
| Run | Humans only | Checkpoint smoke tests by hand, the eval freeze (HUM-10), the explain-back |
| Change | Humans only | Merge, flip repository public (HUM-07), mint tokens (HUM-08), submit (HUM-11) |

Rule: a decision an agent needed is made before the agent's PR is merged, never inferred after (`06` §7.1). Agents never edit `docs/design/`, `.env`, `docs/DECISIONS.md` or `docs/AI_USAGE.md` content that records human acts; they append only their own `AI_USAGE.md` row, which the reviewer must then correct to be truthful (section 6).

---

## 2. Role templates

Four hats from `06-build-plan.md` §3.2, each tied to the workstream prefixes of §5 (INF, GR, ING, AG, WEB, EV, DOC, HUM). The names are a template; a person may hold several hats. The submission form must still state each member's contribution (PRD-FR-053).

| Id | Role | Technical scope | Human-only tasks held | Must be able to explain without notes |
|---|---|---|---|---|
| TEAM-R-01 | **Tech lead / graph owner** = H-Lead (required) | Graph schema and keys (GR), architecture and read-only path (INF, AG), scope and cut lines | HUM-01, HUM-02, HUM-07, HUM-08, HUM-11; go/no-go at every checkpoint; `docs/DECISIONS.md`; submission form | Graph model and keys (`03` §3-§5); why each tool is a parameterized template (ADR 0004, 0005); the architecture and the read-only path (`02` §3-§6); the cut lines applied |
| TEAM-R-02 | **Backend and ingestion** = H-Review (required, may be H-Lead) | Code review of ING, GR, AG, INF PRs; keeps `main` green; runs checkpoint smoke tests | HUM-04 (every PR), HUM-05 (MCP attach), CP0-CP8 smoke runs, restore test, HUM-09 organiser | What each sync layer loads, the PII guarantees (ADR 0020), idempotent `MERGE` (ADR 0008), the five judge-path traversals (`03` §15, `docs/QUERIES.md`) |
| TEAM-R-03 | **Frontend and demo** = H-Demo | Review of WEB PRs against `05-ui-brief.md`; README prose; video; form text | DOC-01 edits (every sentence), DOC-03 video, DOC-04 drafts, optional blog, FalkorDB feedback text | The screens and states (`05` §2, §4), the judge path (PRD-FR-049), the shot list (`05` §8), what the video claims and which frozen run backs it |
| TEAM-R-04 | **Eval and QA** = H-Data/Eval | EV workstream review, ground truth, grader sanity | HUM-03 (re-verify 56 ground truths, about 20 min), HUM-06 (16 hand labels, about 45 min), HUM-10 (freeze and sign) | Eval design, predictions versus outcomes, where the graph lost (`04` §8.4), how the judge model was calibrated |

Mapping to workstreams: INF and GR are owned by TEAM-R-01 with TEAM-R-02 reviewing; ING and AG by TEAM-R-02 reviewing; WEB and DOC by TEAM-R-03; EV by TEAM-R-04. "Owned" means accountable for the human decision and review, not for typing code.

### 2.1 Collapsing roles

Hour budget from `06` §3.2 (inference): D1 about 6 h, D2 about 8 h, D3 about 7 h, D4 about 9 h; total about 30 h, about 8 h each with four people.

| Team size | Assignment (**DECISION, veto-able**) | Consequence |
|---|---|---|
| 1 | One person holds TEAM-R-01..04. Review at checkpoints, not per PR; merge in batches of related PRs (`06` §3.2). Agents prepare artefacts; the person decides, runs, signs. | All 30 h on one person: D4 reaches about 9 h of mandatory acts. L1-L3 are pre-scheduled at CP3 (TEAM-WA-19) and PRD-NG-06 is cut completely. Explain-back is a recorded solo session (section 4.4). |
| 2 | Person A: TEAM-R-01 + TEAM-R-04. Person B: TEAM-R-02 + TEAM-R-03. | Review pair is real and the author is never the reviewer (TEAM-WA-19): B is accountable for ING, so A reviews ING PRs. Video and form need A's approval. |
| 3 | A: TEAM-R-01 + TEAM-R-04. B: TEAM-R-02. C: TEAM-R-03. | Alternative: split R-04 to B if A is the bottleneck on D1 evening (HUM-03 sits next to CP1). |
| 4 | One person per role. | Each person also covers one other role at a checkpoint as backup (section 3.2). |

A person may not be their own sole reviewer for a PR that changes a contract (CHR-GOV-03); with a team of one, the contract-change ADR is written first and the review is the next-morning re-read (section 7).

## 3. RACI

R = does the work, A = accountable (one per row), C = consulted, I = informed. AG = AI build agents (R only, never A). Columns are the four hats: **LEAD** (TEAM-R-01), **REV** (R-02), **DEMO** (R-03), **EVAL** (R-04). Where one person holds several hats, the letter of the highest involvement applies.

### 3.1 Workstreams (`06-build-plan.md` §5)

| Workstream / activity | AG | LEAD | REV | DEMO | EVAL | Human evidence |
|---|---|---|---|---|---|---|
| INF infrastructure, CI, deploy (INF-01..06) | R | A | R (review) | I | I | HUM-01, PR reviews, CP0, CP4, CP6 |
| GR graph layer, tools (GR-xx) | R | A | R (review) | I | C (tool names vs eval) | PR reviews, CP1, CP3 |
| ING ingestion, PII scan (ING-xx) | R | C | A | I | C (ground truth impact) | PR reviews, `SyncRun` zero PII hits (PRD-G-07) |
| AG agent, LLM adapter, MCP (AG-xx) | R | A | R (review) | I | C | PR reviews, HUM-05, CP2, CP5 |
| WEB application (WEB-xx) | R | C | R (review) | A | I | PR reviews, CP4 judge-path run by hand |
| EV harness, graders (EV-xx) | R | C | C | I | A | HUM-03, HUM-06, HUM-10 |
| DOC-01 README | R (draft) | R (approve) | C (clean-machine run) | A | C (eval section) | Teammate follows "run it" on a clean machine |
| DOC-02 `DECISIONS.md`, `AI_USAGE.md` | C | A | R | R | R | File history, section 6 |
| DOC-03 video | I | C | C (reads shot list) | A | C (frozen numbers) | `docs/VIDEO.md` |
| DOC-04 submission form | I | A | C | R (text) | C | Confirmation screenshot |
| DOC-05 runbook, NOTICE, DATA, VERIFICATION | R (draft) | I | A | C | I | Restore test recorded |
| Checkpoint go/no-go (CP0-CP8) | I | A | R (runs smoke tests) | C | C | Result post with commit sha, `VERIFICATION.md` |
| Cut-line decisions (`06` §8.3) | I | A | C | C | C | `DECISIONS.md` record, channel announcement |

### 3.2 Submission artefacts (PRD-FR-049..054, `06` §9)

| Artefact | LEAD | REV | DEMO | EVAL | Backup if owner is absent |
|---|---|---|---|---|---|
| Public repository, green `main`, tags `v0.1-t03`, `v0.2-t01`, `v0.3-t02`, `v1.0-submitted` (PRD §9.0) | A | R | I | I | REV |
| README (video and live link at top, judge path, model, queries, depth table, evaluation, who did what) | C | C | A/R | C | LEAD |
| `/judge` page and judge-path questions (STA-04, DEC-07, DEC-01, MH-07, ABS-10) | A | R (runs) | C | R (verifies ground truth) | REV |
| Frozen eval run, `summary.json`, `docs/EVAL.md` | C | I | I | A/R | LEAD |
| `docs/AI_USAGE.md` complete | C | A/R | R | R | LEAD |
| `docs/DECISIONS.md` complete | A/R | C | I | I | REV |
| Explain-back session record (HUM-09) | A | R | R | R | Whole team |
| Live deployment, uptime monitor, restore test | A | R | I | I | REV |
| Demo video, at most 3:00 (public YouTube) | C | C | A/R | C | LEAD |
| Submission form with T03, T01, T02 named, FalkorDB feedback, contributions | A/R | C | R (text) | C | DEMO |
| `/about` AI-disclosure and team-roles text (PRD-FR-042) | A | C | R | C | LEAD |
| Who-did-what statement (section 9) | A | I | I | I | each member signs own lines |

Backup rule (TEAM-WA-01): every row has exactly one A and a named backup, so a missing person never stalls a checkpoint. With team size 1 the backup column is empty and the cut lines apply instead.

## 4. Human-in-the-loop process for Rules 11-13

### 4.1 Per PR (HUM-04)

1. Agent opens a PR from its worktree branch `feat/<task-id>-<slug>` (`06` §3.1) with the PR template filled and **one appended row** in `docs/AI_USAGE.md`.
2. The reviewer (REV, or LEAD when REV is the author of the human edit) checks, in this order: diff stays inside the card's outputs; contracts are honoured; named tests exist and ran; any "Contract issue" section has an ADR before merge; the `AI_USAGE.md` row names a concrete human check.
3. The reviewer runs at least one thing by hand per PR (a smoke command, a screen, a query) and writes what it was in the row.
4. Merge only after the row is truthful. A row that says only "reviewed" without a named check is sent back (`06` §7.2).
5. A PR the reviewer cannot explain is not merged; it is split, simplified or sent back with a question the agent must answer in the PR.

### 4.2 Per decision

A decision is anything that picks between two alternatives that the code or docs depend on. It gets a record in `docs/DECISIONS.md` the same day (HUM-02). Agents propose in the PR description; the decider is LEAD after talking to the people affected (CHR-GOV-01). Numbering: ADR-0004 onward in `docs/DECISIONS.md` (CHR-GOV-02); `docs/design/adr/0001..0021` is the separate pre-event series and is cited as "ADR nnnn" without a hyphen.

### 4.3 What must be human acts, not agent acts

| Act | Task | Why it counts as meaningful participation |
|---|---|---|
| Re-verify 56 ground truths at the ingested SHA | HUM-03 | An agent cannot grade itself (`04` §12) |
| Hand-label 16 DEC answers | HUM-06 | Calibrates the judge model |
| Run checkpoint smoke tests | CP0-CP8 | Hand-run, results recorded |
| Freeze the eval and sign the run id | HUM-10 | Numbers owned by a person |
| Explain-back | HUM-09 | Rules 11-13 rehearsal |

### 4.4 Explain-back (HUM-09, D4 10:00-10:45, PRD-US-20)

Each member explains, without notes, one area and answers two follow-up questions from another member:

| Area | Rehearse from | Suggested owner |
|---|---|---|
| (a) Graph model and keys | `03` §3-§5, README model section | LEAD |
| (b) Five judge-path queries and why graph-native | `03` §15, `docs/QUERIES.md` | REV |
| (c) Architecture and read-only path | `02` §3-§6, README depth table | REV or LEAD |
| (d) Eval design and its losses | `04` §8.4, README Evaluation | EVAL |

Gaps found are fixed in the README or in the person's understanding before the video is recorded. The outcome is one `AI_USAGE.md` row: "explain-back held, by whom, what was corrected". For team size 1 or 2 each person covers two areas and a second reading follows after a break of at least 30 minutes (**DECISION, veto-able**; alternative: record the session on video for the repository, not recommended while the video budget is tight).

### 4.5 Daily log format

Two files, appended at fixed times. Owners write them, not agents (agents may draft a row, the owner edits).

**`docs/AI_USAGE.md`** (existing columns; one row per merged PR and per human act in section 4.3):

| Column | Rule of thumb |
|---|---|
| Date | IST, `YYYY-MM-DD`, task id in Area, e.g. `GR-03 get_kep tool` |
| Area | Files or component touched |
| AI did | Tool and model, what it produced, what it looked up or ran; one to three sentences |
| Humans did | The decision made, the review performed, the test run by hand, the correction made; names or roles, never "reviewed" alone |
| Verified by | The exact commands or smoke lines run and their result |

Event-period rows go under "Event period" of the file. Template-period rows are not edited.

**`docs/DECISIONS.md`** (existing ADR shape: Date, Status, Veto-able, Context, Decision, Reason, Alternatives, Consequences). One record per decision; status changes to "Superseded by ADR-nnnn" instead of editing history.

**Day-end entry in the team channel** (not a file; copy the three lines into the next morning's standup), posted at the last checkpoint of the day:

```
D<n> <HH:MM IST> · last CP passed: CPx (sha) · PRs merged: n (AI_USAGE rows: n)
Decisions today: ADR-00nn.. · Open contract issues: none | <ids>
Tomorrow first: <task id> · Blocked on a human: <who, what>
```

Pass condition: PR count equals `AI_USAGE.md` row count for the day (PRD-G-07).

## 5. Working agreements and IST checkpoints (4-day sprint)

All times IST. Checkpoints from `06-build-plan.md` §2.1 and §6 are fixed; human windows below are **DECISION (veto-able)** proposals that fit the 30-hour budget.

| Day | Human window (default) | Checkpoints | Human-only tasks |
|---|---|---|---|
| D1 Oct 15 | 00:01-03:00 kickoff burst, sleep to 08:00, work 08:00-23:30 | CP0 00:30, CP1 14:00, CP2 23:00 | HUM-01 (00:01), HUM-02 (03:00, B1-B12 as ADRs), HUM-03 (15:00-15:30, after CP1) |
| D2 Oct 16 | 08:00-22:00 | CP3 14:00, CP4 21:00 | HUM-05 (16:30), HUM-07 (20:30, public flip), README skeleton review |
| D3 Oct 17 | 08:00-22:30 | CP5 13:00, CP6 22:00 | HUM-08 (09:00), HUM-06 (11:00-12:00), `docs/SUBMISSION.md` draft (evening) |
| D4 Oct 18 | 07:00-18:30 | CP7 12:00, CP8 18:00, hard stop 19:59 | HUM-09 (10:00-10:45), HUM-10 (11:00-12:00), DOC-03 video (12:00-16:00, uploaded by 16:00), HUM-11 (16:00-18:00) |

Agreements:

| Id | Agreement |
|---|---|
| TEAM-WA-01 | One accountable person per row of section 3; if absent, the named backup acts and the channel is told. |
| TEAM-WA-02 | One task, one branch, one PR (`06` §3.1). Small commits at least hourly, task id in message, no commit dated before 2026-10-15 00:01 IST (CHR-GOV-08). |
| TEAM-WA-03 | Checkpoints are run by hand on a clean clone of `main`, results posted with the commit sha and appended to `docs/VERIFICATION.md`. A checkpoint passes only if every line passes. |
| TEAM-WA-04 | A critical-path slip above three hours triggers the cut lines in order (L1 P1 `kubernetes/kubernetes` tickets, L2 extracted decisions, L3 arm V, L4 tools 17-19, then T01/T02 items; `06` §8.3). Each cut is announced in the channel and recorded in `docs/DECISIONS.md`. The never-cut list (CHR-GOV-05) is not negotiable. |
| TEAM-WA-05 | Delivery order is T03, then T01, then T02 (PRD-OQ-04). No T01 work starts before CP4 passes; no T02 work before CP5 passes, except cards already unblocked on idle agent lanes. |
| TEAM-WA-06 | Contracts C1-C10 are read-only for agents. A contract problem becomes an ADR before code changes (CHR-GOV-03). |
| TEAM-WA-07 | Secrets only in `.env` and CI/VM secrets. Nobody pastes keys, tokens or the FalkorDB password into Discord, a PR or a document. |

Daily rhythm (**DECISION, veto-able**; alternative: no fixed standup with one person): 08:00 five-minute standup (yesterday's last CP, today's CPs, blockers on humans); one 10-minute check after each checkpoint; the day-end entry (section 4.5). Meetings never exceed these.

---

## 6. Communication plan

| Channel | Used for | Rule |
|---|---|---|
| Team channel (private; tool is a team choice, see TEAM-OQ-02) | Checkpoint results, cut-line announcements, day-end entry, blockers, tokens' existence (never values) | Single source of live status. Every checkpoint post carries the commit sha. |
| GitHub PRs and issues | Task-level discussion, "Contract issue" sections, review comments | Decisions that matter are copied into `docs/DECISIONS.md`, not left in a thread |
| `docs/DECISIONS.md` and `docs/AI_USAGE.md` | The permanent record | Owners per section 4.5 |
| Voice/video call | Kickoff (Oct 15 00:01), HUM-09, freeze review, incident handling | Decisions made on calls are written down within 30 minutes |

### 6.1 Discord policy

The two servers are the FalkorDB server and the WeMakeDevs server (the planning notes §1). Joining both is an organiser obligation (CHR-ST-02) and happens on Oct 13 (charter milestone).

| Id | Policy |
|---|---|
| TEAM-WA-08 | At least one member is in each server and watches the announcements channels at 08:00, 12:00, 18:00 and at each CP; the rules page and public API are re-read Oct 14 evening (HUM-00c) and Oct 18 09:00 for judging criteria, kickoff time, form questions and rule updates (PRD-OQ-11, PRD-C-11). |
| TEAM-WA-09 | No private data, tokens, FalkorDB password, API keys or screenshots showing them are posted. The live URL is shared only after CP4 passes. |
| TEAM-WA-10 | No self-promotion spam, no asking judges for hints about scoring, no DMs to mentors during the build unless the organisers invite it. Mentor or organiser advice that changes the plan is recorded as an ADR. |

---

## 7. Fatigue and sleep policy

The schedule is 96 hours, about 30 human-hours of mandatory acts, and the submission lands at 18:00 on the last day. The policy protects the D4 decisions (freeze, video, form), where mistakes are not recoverable.

| Id | Policy (**DECISION, veto-able**; alternative: no fixed windows, rely on individual judgement) |
|---|---|
| TEAM-WA-11 | Each person sleeps at least 6 hours in each of the three nights (Oct 15, 16, 17). Default windows: D1 night 03:00-08:00 after the kickoff burst, then 00:00-07:00 on the other nights. LEAD and REV stagger by at least two hours so a checkpoint is never unattended in a window. On-call exception: TEAM-WA-17. |
| TEAM-WA-12 | No human works more than 14 hours in a row or more than 16 hours in one calendar day. D4 has the longest mandatory span (07:00-18:30); D3 therefore ends at 22:30 at the latest after CP6. |
| TEAM-WA-13 | No merge, public flip, secret rotation or contract change between 00:30 and 07:00 except the D1 kickoff (HUM-01, HUM-02). A failing overnight job waits; agents may keep running only cards with no human gate and queue PRs for the morning. |
| TEAM-WA-14 | Overnight agent runs: allowed D2 and D3 nights (the ingest/eval/DOC-05 runs in the plan); each has a spend cap (CHR-B-06) and a stop condition written in the card. The reviewer reads results after 07:00, not before. |
| TEAM-WA-15 | D4: no new feature after CP7 (12:00); only fixes that block the five judge-path steps. The submission form is sent by 18:00; the hard stop for any fix is 19:59 IST (CHR-C-12). A decision to cut something after 15:00 on D4 is made by LEAD alone, in writing, in five minutes. |
| TEAM-WA-16 | If a person is ill or unavailable for more than 4 hours, the backup (section 3.2) takes the hat and LEAD applies cut lines before asking anyone to work through the night. |
| TEAM-WA-17 | **On-call exception to TEAM-WA-11 and -13 (OPS-049).** At night only the monitor's SEV1 "site down" push wakes the Primary, who may restart or roll back to the last tagged release (OPS-021) and do nothing else; everything else waits for 07:00. A team of fewer than 3 relies on `restart: unless-stopped`, that push and the freeze. |
| TEAM-WA-18 | The explain-back is 45 minutes (D4 10:00-10:45) in every document (CHR-SC-08, PRD-US-20, TST-206). |
| TEAM-WA-19 | **Teams of 1-2.** Cut lines L1-L3 are applied at CP3 (Oct 16 14:00) unless the measured P0 load time and slip are both inside budget, instead of waiting for the TEAM-WA-04 trigger; D4 keeps no more mandatory acts than section 5 lists. The author of a PR never reviews it: with two people the other reviews, and ING (A = REV) is reviewed by LEAD. |

---

## 8. Submission ownership

| Step | Owner (A) | By (IST) | Verification |
|---|---|---|---|
| Re-read rules, form questions, judging criteria | LEAD | Oct 18 09:00 | Notes in channel; the planning notes §1 updated if changed |
| Frozen eval run id written in README and `docs/EVAL.md` | EVAL | Oct 18 12:00 (CP7) | HUM-10 record |
| Explain-back held | LEAD | Oct 18 10:45 | `AI_USAGE.md` row |
| README final, no placeholders, links resolve | DEMO | Oct 18 10:00 draft, 14:00 final | Clean-machine run by REV |
| Video uploaded, at most 3:00, URL bar visible | DEMO | Oct 18 16:00 | Another human watches it against `05` §8 |
| `docs/SUBMISSION.md` text complete (drafted D3 evening) | LEAD | Oct 17 night draft, Oct 18 16:00 final | Every expected field filled |
| Form submitted naming T03, T01 and T02, contributions, feedback | LEAD | Oct 18 18:00 (CP8) | Confirmation screenshot in channel |
| Repository public, video public, live URL answers five judge steps from a clean browser | REV | Oct 18 18:30 | Run by hand; hard stop 19:59 |
| Uptime watched after the hard stop | REV | Oct 18 19:59 onward | External ping every 5 minutes (PRD-G-06) |

The person who presses submit is LEAD; if they are unreachable at 17:00, DEMO submits using the text in `docs/SUBMISSION.md`. Form access (login, team page) is confirmed on D3 so no account problem appears on D4.

---

## 9. "Who did what" statement template

Used verbatim in the README ("Disclosure and who did what"), in the submission form (PRD-FR-053, Rule 5) and on `/about` (PRD-FR-042). Every member writes and signs their own block; LEAD merges them. Facts only, each line traceable to an `AI_USAGE.md` row, a decision record, a commit or a checkpoint post. No percentages that cannot be traced.

```
KEP Brain · who did what

Team: <n> people. Tracks entered: T03 Company Brain (primary), T01 Agents That
Act on Connected Data, T02 Agent Memory and Coordination.

AI assistance. An AI coding assistant was used as an agent for coding inside
contracts it could not change; the models used to build are the ids recorded in docs/AI_USAGE.md (<copy from that record>),
and at runtime <answering model> and <extraction model>. A template boundary
and pre-event notes are disclosed in README "Provenance" and docs/DECISIONS.md.
Every AI contribution is logged in docs/AI_USAGE.md, one row per merged PR.

<Name or handle> · <roles: tech lead / backend / frontend & demo / eval & QA>
  Decided: <ADR-00nn, ADR-00nn ...>
  Reviewed and merged: <n PRs, task ids or PR numbers>
  Ran by hand: <checkpoints CPx, CPy; HUM-nn tasks>
  Wrote or edited myself: <files or sections>
  Corrected agent output: <1-2 concrete examples with links>
  Can explain: <explain-back area (a)-(d), date, outcome row link>

<repeat per member>

Not done by a human: <what agents produced that no human wrote line by line,
e.g. initial drafts of ingestion parsers, reviewed in PRs <list>>.

Eval integrity. Ground truth re-verified by <name> on 2026-10-15 at <sha>;
16 judge-calibration labels by <name>; frozen run <run id> signed by <name>.
```

Rules for filling it: a member is listed only for acts they did; shared acts name everyone; an act done by an agent is stated as such even if a human approved it; a team of one writes one block and the "Not done by a human" line carries more weight.

---

## 10. Open questions and veto-able decisions

| Id | Question or decision | Default (veto-able) | Alternative | Needed by |
|---|---|---|---|---|
| TEAM-OQ-01 | Roster: how many people, which hats each (PRD-OQ-02, CHR-OQ-02) | Collapse table in section 2.1 | Different split; the form still needs each contribution | Oct 14 |
| TEAM-OQ-02 | Team channel tool and Discord handles of the member(s) watching the servers | Any private group chat plus the two Discord servers | A Discord thread in a private server | Oct 14 |
| TEAM-OQ-03 | Human windows and sleep windows in sections 5 and 7 | D1 kickoff burst then 03:00-08:00 sleep; 00:00-07:00 afterwards; 14 h consecutive and 16 h daily caps | Stay awake through the D1 kickoff night and start CP1 earlier; costs fatigue on D2 | Oct 14 |
| TEAM-OQ-04 | Solo or pair explain-back format (section 4.4) | Two areas per person plus a delayed second reading | Recorded session | Oct 17 |
| TEAM-OQ-05 | Numbering of ADRs between `docs/design/adr/` (0001-0021) and `docs/DECISIONS.md` (ADR-0001-0003, event ADR-0004 onward) can collide in citations | Cite design records as "ADR nnnn" and event records as "ADR-00nn" (CHR-GOV-02) | Prefix event records with `EVT-` | Oct 14 |
| TEAM-OQ-06 | Human hours: whether the 30 h estimate (inference, `06` §3.2) is realistic for the actual roster | Re-estimate after the roster is known and apply early cut lines for a team of 1-2 | Extend human windows within TEAM-WA-11/12 limits | Oct 14 |
