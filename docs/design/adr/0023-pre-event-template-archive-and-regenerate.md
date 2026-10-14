# ADR 0023 · Pre-event template: archive it, ask the organisers, regenerate the scaffold after kickoff

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d, and the archive step must be done by Oct 14 20:00 IST |
| Date | 2026-10-12 |
| Veto-able | Only with a written "yes" from the organisers received before Oct 14 22:00 IST (alternative below) |
| Related | `02-architecture.md` §2.3, §11.8; `06-build-plan.md` INF-01, CP0, CP1; ADR 0003, ADR 0016, ADR 0026 |

## Context

- Rule 8: "The main coding and design work must begin after the hackathon starts. You may discuss ideas, create notes, sketch the graph model, or prepare diagrams beforehand" (https://www.wemakedevs.org/hackathons/falkordb/rules).
- FAQ, "Can I continue an existing project?": "You may reuse general libraries, templates, and infrastructure." and "The submission and its main FalkorDB implementation must be new work completed during the event." (https://www.wemakedevs.org/hackathons/falkordb, VERIFIED 2026-10-12; on the main event page, not on `/rules`).
- The team's own constraint (`FABLE_CONTEXT.md` §0): "Not before the start: code, scaffolding, a git repo, or the UI build."
- OBSERVED 2026-10-12 (file modification times): a generic FastAPI + Next.js + FalkorDB template was written into `D:\kep-brain` between 2026-10-11 22:30 and 2026-10-12 08:39 IST, by the same AI assistant, for this event and this fixed stack. It contains `apps/api/src/app/*.py` including a FalkorDB connection module with `GRAPH.LIST` readiness, executed tests and caches, `apps/web/src/**`, a Compose file with a FalkorDB service and CI with a FalkorDB service container. The build plan v1.1 commits it as the baseline at 00:01 IST.

The template is arguably "general infrastructure" under the FAQ. It is also, unarguably, scaffolding under the team's own rule, and part of it is FalkorDB connection code, which sits close to "the main FalkorDB implementation". If an organiser ruled against it after kickoff, the plan had no slot to rebuild.

## Decision

1. **Archive (H-Lead, by Oct 14 20:00 IST):** move `apps/`, `docker-compose.yml`, `.github/`, `.pre-commit-config.yaml`, `.prettierignore`, `.editorconfig`, `.gitattributes`, `.gitignore`, `.env.example`, `LICENSE` and the template `README.md`, plus the template's `docs/DECISIONS.md` and `docs/AI_USAGE.md`, to `D:\kep-brain-template-archive\2026-10-12\`, outside any repository; it is not read during the event. `docs/` (notes) and `.recon/` (data cache, never committed) stay, except the template's `docs/DECISIONS.md` and `docs/AI_USAGE.md`, which are archived above.
2. **Ask (H-Lead, by Oct 14 18:00 IST):** in writing (WeMakeDevs Discord help channel or the event contact address): "We prepared a self-authored, domain-free FastAPI + Next.js + FalkorDB template on Oct 11–12. May we use it as our starting point?" Archive the question and the answer verbatim in `docs/organiser-answers.md`.
3. **Regenerate (from 00:01 IST Oct 15, INF-01):** `git init`; **commit 1** contains only `docs/`, message "Pre-event notes (Rule 8: notes, graph-model sketches, diagrams)", so the boundary is visible in `git log`; then the scaffold from public generators (`uv init` for `apps/api`, `pnpm create next-app@16.4.0` for `apps/web`), followed by small commits for settings, error envelope, request-id middleware, the FalkorDB role clients, Compose and CI, written against ADR 0003, `02-architecture.md` and `06` §4, by humans and at most three agent lanes (ADR 0026).
4. **Schedule:** ≈ 3 hours on the D1 critical path; CP1 moves from 14:00 to D1 19:00 IST.
5. **Disclosure:** the README's provenance section states that a template was prepared before the event, archived unused, and that the repository's code starts after 00:01 IST on Oct 15.

## Alternatives considered

- **Keep the template as the baseline commit** (the v1.1 build plan): saves ≈ 3 hours. Allowed only if the organisers answer "yes" in writing before Oct 14 22:00 IST; then H-Lead records a dated ADR in `docs/DECISIONS.md` with the answer and the residual risk accepted, and commit 1 still contains notes only, with the template as commit 2 labelled as such.
- **Keep the template and rely on the FAQ alone**: the team's own constraint and the "main FalkorDB implementation" clause make this the riskiest option for a 1–2 hour saving.
- **Regenerate by copying the archive file by file**: indistinguishable from keeping it; rejected.

## Consequences

- The first commit is notes only; no code in the repository predates 00:01 IST.
- D1 loses about three hours; the night lanes absorb most of it.
- Review note: the review estimated the rebuild at 1–2 hours; the plan budgets 3 because the role clients, the five-user ACL init and the CI service container must be rewritten carefully, not quickly.

## Revision 2026-10-12

New (design review R1, R17).
