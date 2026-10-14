# ADR 0001 · Record architecture decisions as MADR files

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead writes their name here at HUM-00d (Oct 14) |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | No (process only) |
| Related | `02-architecture.md` §2.4, §18; ADR 0026 |

## Context

Hackathon Rules 11–13 require the team to explain "the graph model, the queries, the project architecture, and the technical decisions behind them", and projects "entirely generated using AI without meaningful participant contribution, verification, or technical understanding may be rejected" (https://www.wemakedevs.org/hackathons/falkordb/rules). The team needs one place where every non-obvious choice, its alternatives and its consequences are written down so any member can defend it, and where a veto is a one-line edit. These ADRs were drafted by an AI assistant before kickoff; that is disclosed, and it means none of them is a team decision until a named person makes it.

## Decision

- Every architecturally significant decision gets one Markdown file in `docs/design/adr/` named `NNNN-short-title.md`, MADR style: Context, Decision, Alternatives considered, Consequences, and a header table with Status, Date, Veto-able and Related.
- Status values: **Proposed**, **Accepted (by <name>, <date>)**, **Superseded by NNNN**, **Rejected (by <name>, <date>)**. An ADR drafted by an AI is Proposed until H-Lead (or the member who owns the area, ADR 0026) ratifies or vetoes it and writes their name and the date into Status. Ratification of the pre-event set happens at HUM-00d on Oct 14.
- Before 2026-10-15 00:01 IST, Proposed ADRs are revised in place, each revision recorded in a "Revision" section at the end. From kickoff on, an ADR is never edited except to change Status; a change is a new ADR that supersedes the old one.
- During the event, `docs/DECISIONS.md` is the team's running log: it links to these files and records event-time decisions (B1–B24 of `06-build-plan.md` and later ones) with the human decider.

## Alternatives considered

- Decisions inline in the architecture document only: harder to veto individually and to cite in the submission form.
- No ADRs, rely on commit messages: fails the "explain your technical decisions" requirement.
- Mark AI-drafted ADRs "Accepted" as v1 did: misstates who decided, which is exactly what Rule 13 asks about.

## Consequences

- Each ADR costs minutes to write and seconds to veto.
- `docs/AI_USAGE.md` can point at the Status line of each ADR to show which decisions humans made, changed or rejected.

## Revision 2026-10-12

Status changed from "Accepted" to "Proposed" for this and every pre-event ADR; the ratification rule and the in-place revision rule before kickoff were added (design review R2, R7).
