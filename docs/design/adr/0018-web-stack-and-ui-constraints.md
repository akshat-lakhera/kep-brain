# ADR 0018 · Web stack and UI constraints

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Framework fixed by the team; versions, routes and the graph library awaiting ratification by H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Versions, the v1 route set and Cytoscape.js: yes. Light neutral UI: no |
| Related | `02-architecture.md` §4.1, §6.4, §12; `05-ui-brief.md` §2–§4, §7; ADR 0009, ADR 0025 |

## Context

Fixed: Next.js App Router, TypeScript, Tailwind; light, neutral, professional UI; no dark neon, no decorative gradients. On 2026-10-11: `next` 16.4.0, `react`/`react-dom` 19.3.0; `create-next-app@16.4.0` declares `typescript: "^5"`, `tailwindcss: "^4"`, `eslint: "^9"`, `@types/node: "^20"`, `@types/react: "^19"` (`packages/create-next-app/templates/index.ts` at v16.4.0); latest in those ranges: typescript 5.9.3, tailwindcss 4.3.3, eslint 9.39.5. Node 24.21.0 LTS; pnpm 12.11.2. The web app is generated with `pnpm create next-app@16.4.0` after kickoff (ADR 0023).

## Decision

- Pins: next 16.4.0, react/react-dom 19.3.0, typescript 5.9.3, tailwindcss 4.3.3 with `@tailwindcss/postcss` 4.3.3, eslint 9.39.5 + eslint-config-next 16.4.0, vitest 5.0.3, @playwright/test 1.64.0, cytoscape 3.34.3, cytoscape-dagre 4.0.1, cytoscape-fcose 2.2.0, d3-scale 4.0.2, d3-array 3.2.4. TypeScript 6/7 are not adopted until `create-next-app` moves its range.
- **v1 routes**: Ask `/`; Audit `/audit` (findings with both sides, what changed since a release, sync status, the draft-issue dialog); KEP `/explore/kep/{n}` (card, decision timeline, lineage graph); Memory `/memory` (this user's memory, the shared findings board, agent handoffs, Forget everything); Eval `/eval`; Judge `/judge`; About `/about`. Deferred with their tools: `/explore`, `/explore/person/{handle}`, `/explore/sig/{dir}`.
- The Ask page consumes `POST /v1/ask/stream` (SSE over `fetch` + `ReadableStream`): the tool trace, path and citations render live; the answer text appears only after the server's validation, preceded by a visible `checking` phase (ADR 0009). An abstention renders as a first-class result, never as a retracted answer.
- Same-origin `/api/*` through Caddy (prod) or Next.js `rewrites` (dev); no API tokens in the browser; the memory id in `localStorage` (`kep.memoryId`) travels as `X-Kep-Memory-Id`.
- Graph rendering: Cytoscape.js in a small own wrapper; `dagre` left-to-right for Ask paths and KEP lineage (identical on every run and in the video); `fcose` only for the findings board (cap 200); node type by shape plus a text badge, never by colour alone. Eval charts in plain SVG with a table twin per figure. No WebGL, no charting or animation libraries.
- Visual system per `05` §3; works at phone width; light default with a plain dark counterpart.
- TypeScript API types generated from the OpenAPI document, checked in and diffed in CI.

## Alternatives considered

- An SVG force layout: never settles identically, so the hero path would differ between runs and in the video.
- sigma.js 4.0.0: WebGL, built for thousands of nodes we do not show.
- Streaming raw answer tokens (v1): shows unvalidated text (ADR 0009).
- All ten routes of `05` v1: pages for deferred tools would be empty or half-built (ADR 0025).

## Consequences

- `pnpm create next-app@16.4.0` on 2026-10-15 yields exactly these ranges; the lockfile fixes the rest.
- The Judge page is the first thing the README links to.

## Revision 2026-10-12

v1 route set narrowed; Freshness reframed as the Audit page; validated reveal on Ask; findings board on Memory (design review R5, R6, R11).
