# ADR 0003 · One repository, one Python package with four entrypoints, separate web app

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Yes (a polyrepo or a Node MCP server are the obvious alternatives) |
| Related | `02-architecture.md` §2.2, §2.3, §4; `06-build-plan.md` B1; ADR 0013, ADR 0016, ADR 0023 |

## Context

Five runtime roles exist: the HTTP API with the Q&A agent, the ingestion and analytics worker, the freshness agent, the MCP server and the web app. The tool registry, role clients, schema, Pydantic models and PII scrubber are shared by the four Python roles. Judges clone and run the repository. The scaffold is generated after kickoff from public generators (ADR 0023); this ADR is the contract that generation follows.

## Decision

- One public repository `kep-brain`: `apps/api` (a `uv` project, Python package `app`, Python 3.12 via `.python-version`), `apps/web` (pnpm, Next.js), `deploy/` (production Compose file, Caddyfile, `acl-init` assets), `evals/` (question set and runs), `docs/`, `.github/workflows/`, root `docker-compose.yml` (what a judge runs).
- Package `app` has three process entrypoints, all from one image: `python -m app` (uvicorn, the api), `python -m app.worker <command>` (`schema apply`, `sync`, `derive`, `analytics`, `detect`, `schedule`, `eval`, `memory-gc`, `tools export`, `pii-scan`, `llm-check`), `python -m app.mcp [--transport streamable-http|stdio]`. Compose runs them with `command:` overrides.
- Module boundaries inside `app`, enforced by an import-graph test: `schema`, `graph` (one client module per ACL identity: `reader`, `memory`, `ops_writes`, `writer`), `tools` (one module per tool, reader client only), `agent` (planner, provider adapter, prompts, validator; imports `tools` and `graph.reader` only), `memory` (`graph.memory`), `ops_writes` (`graph.ops_writes`; the four `kb_ops` templates), `ingest` and `worker` (`graph.writer`), `api` (routers, middleware, errors), `mcp`. Only `ingest`/`worker` import the writer client; only `ops_writes` imports the `kb_ops` client; `agent` and `tools` import neither.
- Tooling: `uv` 0.13.0 (lockfile committed), ruff 0.17.0, mypy 2.4.0 strict; pnpm 12.11.2 (`packageManager` field), Node 24.21.0 LTS.

## Alternatives considered

- A differently named package with a single custom CLI (v1 of this ADR): rejected by B1 for one convention across the plan; the name carries no meaning a judge needs.
- Separate repositories per service: more CI, harder for judges, no shared models.
- MCP server in TypeScript reusing FalkorDB's server: rejected in ADR 0013 (free-form Cypher).
- Freshness agent inside the worker process: one service fewer, but the worker holds `kb_writer`, and no process that runs an LLM loop may hold a credential that writes `kep` (ADR 0024).
- One process for api and worker: a heavy ingestion would compete with request latency and share the writer credential with the LLM-facing process.

## Consequences

- One image for four Python roles keeps builds fast and versions identical.
- The import-graph test makes the identity split (ADR 0005, 0022, 0024) structural rather than a convention.

## Revision 2026-10-12

Layout aligned with `06` B1 (`apps/api`, package `app`, `python -m` entrypoints); fourth entrypoint `app.agent_service` added; identity modules and import rules spelled out; the scaffold is generated after kickoff (design review R1, R7, R13).
