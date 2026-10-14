# ADR 0020 · Personal data handling under Rule 6

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Storing `Person.name`/`company` from `sigs.yaml`: yes. E-mail stripping and the erasure path: no |
| Related | `02-architecture.md` §9.5, §10.3; `03-graph-model.md` §9; ADR 0002, ADR 0007, ADR 0011, ADR 0024 |

## Context

Rule 6: use only public, synthetic or own data; nothing "private, login-protected, paywalled, personal, or otherwise restricted"; strip e-mails and personal details. `sigs.yaml` contains 205 e-mail addresses (145 unique), 4 private mailing lists and 32 meeting URLs with embedded `pwd=` parameters (`01` §4.4). The commits API returns author and committer e-mails; commit messages carry `Signed-off-by` trailers; comments may contain addresses. Per-user memory stores what users ask; `Finding` nodes in `kep` store agent-written summaries of public records.

## Decision

- **Never stored**: e-mail addresses of any kind. `email`, `private_mailing_list` and meeting `url` keys in `sigs.yaml` dropped at parse time; commit e-mails never read (`git log` formats without e-mail fields; GraphQL queries request `login` only); `/users/{login}` never called; all free text scrubbed (addresses → `[email removed]`; `Signed-off-by:`/`Co-authored-by:` lines dropped) **before** hashing; nothing login-gated fetched (Slack, Google Groups, Zoom, Google Docs stored as URLs only); forks excluded; a post-sync invariant scan over every text property fails the `SyncRun` on any address (`03` §9 G4).
- **Stored**: the GitHub login (lower-cased), and `name`/`company` only for `sigs.yaml` leadership entries while `STORE_PERSON_NAME_COMPANY=true`.
- **Licensing** (`01` D11, B10): Apache-2.0 files are cloned at a pinned SHA at run time and credited in `NOTICE`; issue and PR comments are fetched into FalkorDB at deploy time and never committed to the repository, including any raw-response cache; excerpts are attributed and linked; the README documents a removal-request path.
- **Per-user memory**: `mem:<ULID>` holds questions, answers and facts about interests; no account, no e-mail, no IP. The Memory page shows all of it; `DELETE /v1/memory/me` erases it synchronously (`GRAPH.DELETE` as `kb_memory`, ADR 0002) and writes an `AuditEvent` with a hashed id; retention 90 days.
- **Shared findings**: `Finding` nodes in `kep` describe public records and cite public evidence; the freshness agent's summaries pass the PII scrubber before they are written; a finding of kind `declared_approver_never_approved` names a public role holder and is shown in the audit but never turned into an action (ADR 0021).
- **Logs**: memory ids only as a SHA-256 prefix; parameter values never logged.

## Alternatives considered

- Store everything and redact at display time: violates "strip emails" at rest.
- Drop names and companies entirely: safest; costs the "who is this person" affordance. Left to the team.

## Consequences

- Hypothesis test: the scrubber leaves no addresses; integration test: no node carries an e-mail-shaped value after ingesting the fixture with planted addresses; ACL test: erasure as `kb_memory` removes the graph.

## Revision 2026-10-12

Erasure path made executable (`kb_memory` grants) and audited; clone at run time instead of a committed snapshot (B10); shared-memory rules; cache never committed (design review R4, R8, R10, R12).
