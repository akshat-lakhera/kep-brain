# KEP Brain · Risk register

## 0. Document control
| | |
|---|---|
| Document | `docs/ops/risk-register.md` |
| Status | v0.1 draft for team sign-off (H-Lead). Pre-kickoff note (Rule 8 allows notes before 2026-10-15 00:01 IST); no code, scripts or manifests. |
| Date | 2026-10-12 (IST) |
| Owner | H-Lead; risk owners are roles of the `06-build-plan.md` §3.2 template (one person may hold all). |
| Length cap | 150 lines |
| Relation to `06` §8.1 | The build plan's `R1`-`R17` stay the design-time list. `RSK-nnn` here is the product-document list; each row maps to the `R` id it extends and to the requirement and test ids that already carry its control. No control is invented here: a row without a control names the gap. |

Scales (INFERENCE, not measured): Likelihood and Impact are L / M / H. **Status** is `open` until the named test passes; the register is re-read at every checkpoint go/no-go (CP1-CP8).

## 1. Register
| Id | Risk | `06` | L / I | Controls (requirements, then tests) | Trigger and response | Owner |
|---|---|---|---|---|---|---|
| RSK-001 | **LLM provider outage, key leak or spend runaway** | R6 | M / H | TRD-TR-028, TRD-SR-022, TRD-SR-023, TRD-NFR-019, TRD-NFR-021; OPS-045, OPS-056 (combined $150 cap, two keys), OPS §8.2, §8.5; TST-026, TST-027, TST-162 | Alert at $75 and $120 combined; degraded banner keeps Explore, Freshness, Eval, Judge working | H-Lead |
| RSK-002 | **FalkorDB feature missing or different in 4.22.0** (UNVERIFIED list of TRD-OQ-15 and `06` R2) | R2 | H / H | Hour-one check TRD-TR-072; fallbacks in TRD-DR-016, TRD-SR-015, TRD-SR-016; TST-194, TST-150, TST-154 | A failed check on Oct 15 switches to the stated fallback and is logged in `docs/DECISIONS.md` | H-Lead |
| RSK-003 | **Upstream drift** (release v1.38 in flight changes a judge-path answer) | R8, R15 | H / L | TRD-DR-008 (pinned SHA); HUM-03; TST-101; frozen snapshot mode TRD-TR-024, OPS D7; TST-058 | A value moves: swap the judge-path step on Oct 15 only; later it is a logged known change | H-Data/Eval |
| RSK-004 | **GitHub rate limits, secondary limits or token failure** | R4 | M / M | TRD-TR-010, TRD-DR-003 (floor 200), TRD-NFR-014; OPS §8.3, OPS-016; TST-009 | A failed run keeps cursors and resumes; cut line L1 if the initial load is blocked before CP4 | H-Review |
| RSK-005 | **PII or e-mail reaches the graph or repository** (Rule 6, disqualification) | R11 | L / H | TRD-TR-006, TRD-DR-010, ADR 0020; OPS-028, OPS-048; TST-003, TST-007, TST-170 | Any hit fails the sync and blocks the swap; fix the mapping, rerun | H-Review |
| RSK-006 | **Single-VM outage or data loss** | R3, R10 | M / H | TRD-NFR-018, TRD-NFR-026; OPS-030..035, OPS §6.4 drills, §8.1; TST-182, TST-183 | Restore per OPS §6.5; the public corpus is rebuildable, only `mem:*` and `ops` are not | H-Lead |
| RSK-007 | **Team fatigue or a team of one** (four days, about 30 human-hours) | R16 | H / M | TEAM-WA-11..17, TEAM-WA-04 (cut lines), pre-scheduled cuts for teams of 1-2 (TEAM-WA-19); OPS-049 night policy | A missed checkpoint is absorbed by the next; CP4 and CP8 are fixed | H-Lead |
| RSK-008 | **Rule 8 / Rule 9 template position questioned** | R12 | L / H | CHR-C-01, CHR-CMP-01, PRD-C-01; first commit at or after 00:01 (CHR-GOV-08); organiser answer recorded as an ADR (CHR-OQ-05); TST-185 | A judge asks: point at the first commit, the disclosure and the recorded organiser answer | H-Lead |
| RSK-009 | **Abuse of the public no-sign-up surface** (prompt injection, cost drain, scraping, action abuse) | R17 | M / H | TRD-SR-019, 020, 022, 038; ADR 0021; TST-150..160, TST-162 | Lower limits by environment; Caddy block rule; revoke key as last resort (OPS §8.5) | H-Review |
| RSK-010 | **Unmeasured latency targets missed** (TRD-NFR-001, TRD-NFR-005) | - | M / M | Calibration at CP2, frozen at CP4, reported as measured at CP7 (TRD-OQ-04); TST-141 | Publish the miss in README and `/eval` | H-Data/Eval |
| RSK-011 | **Atomic-claim and per-user-graph assumptions do not hold** (single-writer serialisation per graph; asynchronous constraint creation on new `mem:*` graphs) | R2 | M / M | TRD-TR-049, TRD-DR-019, TRD-TR-072 fallbacks; TST-138, TST-144, TST-145, TST-194 | Switch to the version-checked claim or the template-graph copy; cut lines L6, L7 | H-Lead |
| RSK-012 | **Graph-scale estimates disagree** (`02` §9.6 versus `03` §16), so VM and memory sizing and the README counts could be wrong | R3 | M / M | TRD §2 note; counts measured on Oct 15; OPS §3.1; TST-014 (recorded, not asserted against either estimate) | Quote only measured counts; resize per OPS D1 | H-Lead |
| RSK-013 | **Rules 11-13 doubt** (AI-generated without understanding; disclosure inaccurate) | R13 | M / H | CHR-CMP-03/04, TEAM §4, HUM-04, HUM-09 (45-minute explain-back); `docs/AI_USAGE.md` is the single record of model ids (CHR-OQ-13); TST-186, TST-206 | An unexplained area is fixed in the README or in the person before the video | H-Lead |
| RSK-014 | **Provider or library behaviour differs from the 2026-10-06 cache** (`tool_choice`, `fallbacks`, pinned `anthropic`, `mcp`, Next versions) | R6 | M / M | TRD-TR-027 (UNVERIFIED), TRD-TR-072 re-check before CP2; recorded double with a `refusal` stop | Use the stated fallback (`tool_choice: auto`, no beta header) and log it | H-Review |
| RSK-015 | **Graph view too slow above 200 nodes** | R14 | L / L | TRD-NFR-009 (the single layout threshold), PRD-FR-038; TST-074 | Lower the default cap and state the measurement | H-Demo |
| RSK-016 | **Removal request cannot be honoured while the schedule is frozen** (Rule 6 community obligation) | R11 | L / M | Suppression sync TRD-TR-073, TRD-SR-045; OPS-063; TST-192 | Operator-run suppression sync; backups expire in 7 days | H-Review |
| RSK-017 | **Public MCP judge token abused or leaked beyond its purpose** | R17 | M / M | TRD-SR-006 (read-only, rate-limited, rotated after results), TRD-SR-035; OPS D5, OPS-062; TST-115, TST-169 | Rotate the token; judges fall back to local Compose | H-Review |
| RSK-018 | **A freeze rule conflicts with a recording or fix** (deploys during recording, key changes) | R10 | M / M | OPS §11 (F2 and F3, degraded shot on local stack); DMO-REC-08, DMO-RDY-34; test-plan §4.3 | Record against local Compose and caption it; roll back to the tagged release only if the site is down | H-Demo |

## 2. Review log
| Date | Reviewer | Change |
|---|---|---|
| 2026-10-12 | H-Lead (draft) | Register created from the TRD §13 topics, `06` §8.1, the threat model and the document review findings |

Rows are added, never renumbered. A risk that fires gets a three-line note under the checkpoint it fired at (cause, fix, follow-up) and a `docs/DECISIONS.md` row if a decision changed.
