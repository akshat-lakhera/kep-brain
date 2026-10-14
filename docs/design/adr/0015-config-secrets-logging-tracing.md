# ADR 0015 · Configuration, secrets, logging and tracing conventions

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12; adopts `06-build-plan.md` B2, B3, B11, B15). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Library choices and OpenTelemetry default yes; env-only config and JSON logs no |
| Related | `02-architecture.md` §11; ADR 0002 |

## Context

The engineering bar is production-grade: no hardcoded secrets, structured logs, request ids, an error taxonomy, health and readiness. FalkorDB's OpenTelemetry guide instruments falkordb-py through `opentelemetry-instrumentation-redis` and recommends logging query structure rather than values (https://docs.falkordb.com/operations/opentelemetry). Versions (PyPI, 2026-10-11): pydantic-settings 2.15.0, structlog 26.1.0, opentelemetry-sdk 1.45.1.

## Decision

- **Config**: one `Settings` class (pydantic-settings), **unprefixed** names (B2; the authoritative list is `06` C4 plus `02` §11.1), typed fields and validators (`ACTION_REPO` is `owner/name`, `SIGS` are `sig-*`), fail fast at start; a defined-but-empty value counts as unset. `.env` for dev only; `.env.example` lists names and formats; no config files in images.
- **Secrets**: env only; prod `.env` root-owned, mode 600; every secret a `SecretStr`; CI encrypted secrets; gitleaks CLI v8.30.1 on every PR (B21); the ACL file stores hashes; a structlog processor drops known secret keys and configured secret values; rotation per ADR 0002.
- **Logging**: structlog JSON lines, UTC. Bound per request: `request_id`, `memory_id_hash` (SHA-256 prefix), `route`, `tool`. Per FalkorDB call: tool name, parameter digest, rows, server execution time, `truncated`. Never logged: parameter values, prompt bodies, tokens, rejected answer text above debug level.
- **Request ids**: an inbound `X-Request-ID` is accepted only if it matches `^[A-Za-z0-9._-]{1,128}$`, else a UUIDv7 is generated; echoed in the response.
- **Errors**: one module maps exceptions to the taxonomy in `02` §11.4 (including `capacity_reached`, `graph_timeout`, `forbidden`); envelope `{error: {code, message, request_id, details?}}`; messages from an allow-list; no stack traces in bodies.
- **Tracing**: the OpenTelemetry SDK is wired with a no-op provider by default; setting `OTEL_EXPORTER_OTLP_ENDPOINT` enables OTLP/HTTP export with the FastAPI and Redis instrumentors and manual spans (`agent.plan`, `agent.tool.<name>`, `llm.call`, `memory.write`, `sync.<stage>`). No Jaeger service in v1 (`06` cut line L10 applied by default).
- **Health** (B3, B11, B15): `GET /health` liveness; `GET /ready` = FalkorDB answers as every identity the process holds and the schema is applied, with per-check details only for the admin token; neither is routed by Caddy.

## Alternatives considered

- A settings prefix (v1): two conventions in one environment once the template's unprefixed names exist (B2).
- Prometheus `/metrics`: another surface to secure; request-id logs plus `GRAPH.SLOWLOG` suffice for four days.
- A Jaeger service in dev from day one: one more container to run and explain; the request id already ties a report to its logs.

## Consequences

- Every answer shows its `request_id`; a judge's report maps to one log stream.
- Turning tracing on is one variable.

> **Superseded content (v1 of this ADR).** v1 used the `KEPBRAIN_` prefix, liveness and readiness paths `/healthz` and `/readyz` on the api, and a Jaeger dev profile; replaced as above.

## Revision 2026-10-12

Unprefixed settings; `/health` and `/ready`; readiness checks every held identity; OpenTelemetry no-op by default and Jaeger deferred (design review R6, R7).
