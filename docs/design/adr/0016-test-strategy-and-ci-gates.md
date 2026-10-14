# ADR 0016 · Test strategy and CI gates, including a real FalkorDB and the eval harness

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Tool versions yes; "integration and ACL tests hit a real FalkorDB" no |
| Related | `02-architecture.md` §11.7–§11.8, §20; `04-eval-set.md`; `06-build-plan.md` INF-02, INF-04; ADR 0002, ADR 0005, ADR 0009 |

## Context

Judges clone and run the repository; FalkorDB's judge praised "honesty about failures, and tests". The riskiest properties (read-only enforcement, ACL scoping, idempotency, memory isolation and erasure, single-winner claims, validate-before-reveal) are database or protocol behaviours that mocks cannot prove. Versions (2026-10-11): pytest 9.1.1, pytest-asyncio 1.4.0, hypothesis 6.169.0, respx 0.23.1, ruff 0.17.0, mypy 2.4.0, vitest 5.0.3, @playwright/test 1.64.0.

## Decision

- **Unit**: parsers, the normalisation map, the PII scrubber (Hypothesis), the claim validator (including "no claim may cite a finding or memory id"), tool parameter models, GitHub pacing and GraphQL batching (`respx`), provider translation, the SSE chunker, cursor arithmetic.
- **Integration** (real FalkorDB): the CI `api` job runs against a `falkordb/falkordb:v4.22.0` service container in `FALKORDB_ACL_MODE=single`: schema and constraints reach `OPERATIONAL`; the fixture mini-repository loads twice with identical counts; `RO_QUERY` rejects a write; a slow query hits the timeout; 20 concurrent claimers yield one winner; memory graphs are isolated.
- **ACL** (the `compose` job, real `users.acl`, tests marked `acl` run inside the `api` container): every role user constructs a falkordb-py 1.7.1 client and runs one query; `kb_reader` cannot `GRAPH.QUERY` or read `mem:*`; `DELETE /v1/memory/me` as `kb_memory` removes the key from `GRAPH.LIST` (checked as `default`); `GRAPH.DELETE kep` as `kb_memory` is refused; `GRAPH.CONSTRAINT CREATE` as `kb_memory` succeeds on a `mem:` graph and fails on `kep`; `kb_ops` cannot write `kep`; the rotation procedure runs end to end.
- **Contract**: OpenAPI and `Answer` snapshots; SSE contract tests, including an invalid recorded transcript that must yield zero `token` events and one `done {abstained: true, abstain_reason: "unsupported_claims"}`.
- **Boundaries**: import-graph tests per ADR 0003 and a registry test that the planner holds no `kb_ops` or `kb_memory` caller; a "no second store" dependency and import scan.
- **Eval harness**: `evals/questions.yaml` (the 56 questions of `04`, plus the 8 `MEM` items and the findings precision labels), run with `python -m app.worker eval …`; results under `evals/runs/<utc>/` (frozen run committed); metrics per `04` plus audit precision (detector vs detector + agent) and memory with/without recall. Runs manually against the live LLM; CI runs a tools-only subset with no LLM.
- **Web**: vitest; one Playwright smoke over the five judge-path steps.
- **Load**: `tests/load`, 50 users, 60 s.
- **Docs**: Markdown link check and the retired-names check of `02` §20.
- **CI gates** (required on `main`): `api`, `web`, `compose`, `secrets-scan`, `docs`, and `audit` from CP6. Actions pinned by commit SHA; `permissions: contents: read`; squash merges, linear history. The first commit is at or after 2026-10-15 00:01 IST and contains notes only (ADR 0023).

## Alternatives considered

- testcontainers in the unit job (v1): the template's service-container approach is simpler in CI; ACL tests need the full compose stack anyway.
- Mocking the graph client: proves nothing about `RO_QUERY`, ACL or atomic claims.
- Full LLM eval in CI: costly and non-deterministic.

## Consequences

- Test names double as the README's "what we verified" list.
- The `compose` job is the slowest gate (minutes); it is where the security properties are proven.

> **Superseded content (v1 of this ADR).** v1 described 15–20 eval questions committed under `evals/results/` and testcontainers starting the server image; replaced by `04`'s 56 questions under `evals/runs/` and the CI service container plus the compose job.

## Revision 2026-10-12

Aligned with `04` and `06` (question count, paths, CI topology); ACL, rotation, SSE and boundary tests added; docs check added (design review R7, R8, R9, R10, R11, R13, R14, R16).
