# KEP Brain

Every significant change to Kubernetes goes through a KEP, a Kubernetes Enhancement Proposal: a design document with a metadata file and a tracking issue, owned by a SIG. KEP Brain is a company brain for that process. It loads KEPs, SIG rosters, tracking issues and pull request history from public GitHub into one FalkorDB graph, works out who decided what and on which evidence, flags records that contradict each other, and answers questions with citations or abstains.

[![CI](https://github.com/akshat-lakhera/kep-brain/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/akshat-lakhera/kep-brain/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](apps/api/pyproject.toml)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](apps/web/package.json)
[![FalkorDB 4.22](https://img.shields.io/badge/FalkorDB-4.22-FF66B3)](docker-compose.yml)

![Landing page: the headline, two calls to action and the live graph counts beside a framed screenshot of an answer with its evidence diagram](docs/screenshots/home.png)

## Table of contents

- [The problem](#the-problem)
- [What it does](#what-it-does)
- [Screenshots](#screenshots)
- [How it works](#how-it-works)
  - [Architecture](#architecture)
  - [Graph data model](#graph-data-model)
  - [Graph features used](#graph-features-used)
- [Quick start](#quick-start)
- [Development](#development)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [API overview](#api-overview)
- [Status](#status)
- [Contributing](#contributing)
- [AI assistance](#ai-assistance)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## The problem

Every significant change to Kubernetes goes through a KEP, a Kubernetes Enhancement Proposal. A KEP is a folder in [kubernetes/enhancements](https://github.com/kubernetes/enhancements) with the proposal text and a `kep.yaml` metadata file, plus a tracking issue in the same repository; the issue number is the KEP number. The [KEP process](https://github.com/kubernetes/enhancements/blob/master/keps/sig-architecture/0000-kep-process/README.md) makes `kep.yaml` the record of a KEP's state: `status` is required, must be one of seven values, and the metadata is "critical to clearly communicate the status of a KEP" and "used to support tooling around filtering and display". The same document pairs `replaces` with `superseded-by` on the other KEP and with the `replaced` status.

Nothing enforces that. The state of a KEP is written in several places by different people at different times: `kep.yaml` in a pull request, the tracking issue's state, labels and milestone by the release team, and the replacement declarations in two KEPs. They drift apart, and the drift is invisible to anyone reading one record. On the three SIGs loaded here, 59 pairs of records disagree, across 50 of the 238 KEPs. Forty of those KEPs have a `kep.yaml` that still says `implementable` or `provisional` while their tracking issue is closed, some as far back as 2019. Anyone who filters KEPs by status, as the process says the metadata is for, gets a wrong answer for those.

The questions behind that drift are the questions anyone joining a SIG, running a release or reviewing a proposal asks and cannot answer from one file: who decided this KEP's current state and on what evidence, who approved it, who actually knows this area, what replaced what, what changed since the last release, and which records are stale.

**How KEP Brain tackles it.** It reads every source live from public GitHub into one FalkorDB graph and keeps the history: each state edge carries the interval it was valid for, so "current" and "as of release X" are the same graph with a different filter. From the kep.yaml history it derives who decided each state and links each decision to the commit, the pull request and the approvers. Five predicates written from the process rules above compare the records pairwise and write each disagreement as a `Finding` with both sides, their source URLs and a suggested fix, and the audit page drafts the issue text from that evidence. Questions are answered by an agent that may only use read-only graph tools; a validator checks that every claim cites a record returned in that request and replaces the answer with an abstention if it cannot. Every citation is a graph node with a public GitHub URL, so the answer can be checked in one click.

## What it does

A KEP's state lives in several places at once: the `kep.yaml` file, the tracking issue with its labels and milestones, the pull requests that changed the file, and the KEPs it replaces or is replaced by. KEP Brain puts them in one graph and reads them together.

- **Live ingest from public GitHub.** The worker clones `kubernetes/enhancements` and `kubernetes/community`, reads OWNERS files from `kubernetes/kubernetes` through the GitHub API, and fetches tracking issues, timelines, pull requests and review threads. Every run upserts into the same FalkorDB graph, so re-running is safe.
- **Who decided what, from which evidence.** Every `kep.yaml` revision is diffed field by field. Each status, stage or milestone change becomes a `StatusChange` linked to its commit and pull request. From these, the worker derives `Decision` nodes and attaches the people who approved them and the records that prove it.
- **Contradiction audit.** Five predicates compare a KEP's `kep.yaml` with its tracking issue and its replacement declarations. Each hit is a `Finding` that carries both sides with their public URLs and a lifecycle (`open`, `resolved_upstream`, human verdicts). The audit page can draft an issue body from the evidence. Nothing is ever posted to GitHub.
- **Answers with citations, or abstention.** `POST /v1/ask` runs an agent over a read-only tool catalog. A deterministic validator checks that every claim cites a record returned in that request. If it cannot, the answer is replaced by an abstention. Every citation is a graph node with a public GitHub URL. The Ask page puts the question box first and shows each answer's evidence chain as a force-directed diagram, coloured by node label with the cited nodes ringed, or as a list. Questions about the KEP process and about KEP Brain itself are in scope: both are answered from document sections stored in the graph and cited like any other record.
- **Explore pages.** Search KEPs, open a KEP with its facts, status history, decisions and lineage (drawn with the same diagram), and browse SIGs and people. The Tools page calls any catalog tool directly and draws the records it returned.
- **Per-browser memory.** An anonymous memory id (header `X-Kep-Memory-Id`) selects a small per-user graph that can be inspected and deleted as a unit.
- **MCP server.** The same read-only tools are exposed over Streamable HTTP behind a bearer token, so other agents can query the graph (`/mcp` on the local port in development and through Caddy in the production deploy).

On 2026-10-17 the running instance reported 238 KEPs, 674 people and 59 findings across 50 KEPs in 39,397 nodes and 127,115 edges, for `sig-node`, `sig-scheduling` and `sig-apps` (`GET /v1/meta`, `GET /v1/findings`; ticket data as of 2026-10-15).

## Screenshots

| Landing | Explore |
|---|---|
| ![Landing page: hero text and live graph counts beside a screenshot of an answer with its evidence diagram](docs/screenshots/home.png) | ![Explore page: SIG cards with the loaded SIGs first, and the release dropdown for recent changes](docs/screenshots/explore.png) |

| KEP detail | Audit |
|---|---|
| ![KEP-4671 page on its Decisions tab: each decision with its date, deciders and evidence links](docs/screenshots/kep.png) | ![Audit page with the findings table and by-kind and by-SIG bars](docs/screenshots/audit.png) |

## How it works

### Architecture

```mermaid
flowchart LR
    subgraph Sources
        ENH[kubernetes/enhancements<br/>git clone]
        COM[kubernetes/community<br/>sigs.yaml]
        GH[GitHub API<br/>OWNERS, issues, PRs, reviews]
    end
    subgraph Worker["Worker (python -m app.worker)"]
        W1[schema-apply]
        W2[sync-docs, sync-history,<br/>sync-owners, sync-tickets]
        W3[derive: Decisions,<br/>Findings, PageRank]
    end
    DB[(FalkorDB<br/>graph kep)]
    subgraph API["FastAPI (apps/api)"]
        T[read-only tool catalog]
        A[agent + claim validator]
        H[HTTP /v1]
        M[MCP server]
    end
    WEB[Next.js web<br/>apps/web]
    ENH --> W2
    COM --> W2
    GH --> W2
    W1 --> DB
    W2 --> DB
    W3 --> DB
    DB --> T
    T --> A
    T --> H
    T --> M
    A --> H
    H --> WEB
```

1. **Ingest.** `sync-docs` reads every `kep.yaml`, KEP README and PRR file from the enhancements clone and replays each revision so that state edges get `valid_from` and `valid_to` from commit dates. It also stores the two KEP process documents and the product document shipped with the API (`apps/api/src/app/data/kep_brain.md`, `ingest/product.py`) as `Document` nodes with one `Section` per heading, so "what is a KEP" and "what is KEP Brain" are answered from cited sections. `sync-history` diffs `kep.yaml` revisions into `StatusChange` nodes and maps commits to the pull requests that merged them. `sync-owners` loads OWNERS files and aliases. `sync-tickets` loads tracking issues, their label and milestone timelines, and the pull requests and review discussion behind status changes.
2. **Graph.** Everything lands in one FalkorDB graph named `kep`. Node and relationship names come from an allow-list (`apps/api/src/app/schema/labels.py`), and `schema-apply` creates the indexes and `UNIQUE` and `MANDATORY` constraints.
3. **Derive.** `derive` turns metadata changes into `Decision` nodes (`status_transition`, `withdrawal`, `stage_graduation`, `milestone_retarget`), adds PRR approval and replacement decisions, links each to the people who decided it (`DECIDED_BY`) and the evidence (`EVIDENCED_BY`), evaluates the five contradiction predicates into `Finding` nodes, and stores PageRank on `Person` nodes.
4. **Serve.** The API reads the `kep` graph with `GRAPH.RO_QUERY` only; its writes go to other graphs: `POST /v1/ask` stores validated answers in the `ops` graph (answer cache) and episodes in the caller's `mem:<id>` graph, and the `DELETE` memory and cache routes remove from those. The cache is keyed by question and graph version and serves every caller, with or without a memory id; a hit replays the recorded tool calls, evidence graph and citations instead of calling the model. The web app, the answering agent and the MCP server all go through the same parameterised tool catalog.

### Graph data model

Node labels (`NODE_LABELS` in `labels.py`):

| Group | Labels |
|---|---|
| Organisation | `SIG`, `WorkingGroup`, `Committee`, `Subproject`, `Person`, `Alias`, `OwnersFile` |
| Documents | `KEP`, `Document`, `Section`, `FeatureGate`, `Component`, `Metric`, `Release`, `Label`, `ExternalRef` |
| Activity | `Commit`, `PullRequest`, `Issue`, `Ticket`, `Review`, `Comment`, `StatusChange` |
| Derived | `Decision`, `Finding`, `AnswerCache` |
| Operations | `SyncRun`, `WorkerHeartbeat` |

Relationship types split into two families:

- **State relationships** (`STATE_RELS`) carry a validity interval. Examples: `CHAIRS`, `TECH_LEAD`, `APPROVER`, `REVIEWER`, `MEMBER_OF`, `OWNED_BY`, `AUTHORED`, `APPROVES`, `PRR_APPROVED`, `REPLACES`, `SUPERSEDED_BY`, `GATED_BY`, `ENABLED_IN`, `TARGETS`, `TRACKED_BY`, `LABELED`, `MILESTONED`.
- **Other relationships** (`OTHER_RELS`) describe structure and provenance. Examples: `HAS_DOCUMENT`, `HAS_SECTION`, `NEXT`, `MENTIONS`, `CHANGED`, `HAS_EVENT`, `IN_COMMIT`, `IN_PR`, `PREVIOUS`, `REVERSES`, `DECIDED_BY`, `EVIDENCED_BY`, `FROM_CHANGE`, `OPENED`, `MERGED`, `COMMENTED`, `REPLIES_TO`, `REFERENCES`, `IMPLEMENTS`, `RELATED_KEP`.

KEP statuses are `provisional`, `implementable`, `implemented`, `deferred`, `rejected`, `withdrawn`, `replaced`. Stages are `alpha`, `beta`, `stable`, `deprecated`, `disabled`, `removed`.

Finding kinds (`FINDING_KINDS`):

| Kind | Meaning |
|---|---|
| `active_status_closed_issue` | `kep.yaml` says the KEP is active, but its tracking issue is closed |
| `terminal_status_future_targets` | The KEP is in a terminal status but still targets a future release |
| `one_sided_replacement` | One KEP declares `replaces` or `superseded-by` and the other side does not agree |
| `stage_mismatch` | The stage in `kep.yaml` and the stage label on the issue differ |
| `milestone_mismatch` | The milestone in `kep.yaml` and the milestone on the issue differ |

The checks are rule-based, and some hits are tolerated conventions rather than mistakes, so the suggested fix on a `Finding` says so instead of prescribing a value (`ingest/findings.py`). A tracking issue closed by the lifecycle bot for inactivity, or closed before 2022-05-19 (when GitHub introduced close reasons and backfilled every older closure as `completed`), gets `review_status` rather than a status to set, and the issue side of such an older finding reads "closed (reason not recorded)". A stage label on a closed issue when `kep.yaml` changed after the close, and any milestone on a closed issue, are frozen history: `none_historical_label`. An open issue milestoned to the release in development or the one after it is the normal mid-cycle state, so the fix is `in_flight_wait_for_freeze`.

### Graph features used

| Feature | Where | Why |
|---|---|---|
| Validity intervals on state edges (`valid_from`, `valid_to`) | `db/batch.py`, `ingest/*.py`, `api/*.py` | "Current" is `coalesce(r.valid_to, $open) = $open` with the open sentinel `2100-01-01T00:00:00Z`. History is the same edges without the filter. Edges that disappear from a source are closed, not deleted. |
| `MERGE` upserts in `UNWIND` batches | `db/batch.py` | Deterministic keys make every sync idempotent. |
| `UNIQUE` and `MANDATORY` constraints, range indexes | `schema/apply.py` | The database enforces idempotent ingest and keeps key lookups indexed. |
| `GRAPH.RO_QUERY` with per-query timeouts | `db/falkordb.py` | Request handlers cannot write, and a slow question cannot hold a connection. |
| `algo.pageRank` over `DECIDED_BY` | `ingest/derive.py` (`write_pagerank`) | Stores an influence score on each `Person` at derive time so `rank_people` reads it instead of recomputing. |
| `algo.SPpaths` | `tools/t01/graph_algos.py` (`path_between`) | Shortest explainable connection between two entities. |
| Pattern comprehensions | `api/findings.py`, `api/keps.py`, `tools/` | One query returns a KEP with its issue, owners and evidence as lists. |
| One graph per memory id | `memory/store.py` | Per-user memory is isolated from the shared `kep` graph and deletable as a unit. |
| `GRAPH.COPY` | `scripts/graph_swap.py` | Blue-green reload: a graph loaded as `kep_fresh` is copied in as `kep`, the previous graph is kept as `kep_old` and the answer cache is cleared. |

## Quick start

You need Docker with the Compose plugin.

```bash
git clone https://github.com/akshat-lakhera/kep-brain.git
cd kep-brain
cp .env.example .env
```

Edit `.env`. The variables that matter for a first run:

- `FALKORDB_PASSWORD` (required): a long random password.
- `MCP_TOKEN` (required by the `mcp` service): at least 32 random bytes.
- `GITHUB_TOKEN` (required by `worker all`): a read-only token; a classic token with no scopes is enough. `sync-owners` and `sync-tickets` read the GitHub API and stop with an error without it (unless the `gh` CLI is logged in, which the image does not have).
- `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `LLM_MODEL` (any OpenAI-compatible endpoint): needed for `POST /v1/ask`. Everything else works without them.
- `SIGS`: the SIG directories in scope. The default is `sig-node,sig-scheduling,sig-apps`.

Start the stack and build the graph:

```bash
docker compose up -d falkordb api web mcp
docker compose run --rm worker all
```

The first `all` run clones the public repositories into the worker volume and takes a while. Later runs fetch and only re-read changed sources. The `worker` service in `docker-compose.yml` runs `schedule --interval-minutes 1440` to keep the graph fresh.

- Web: http://localhost:3000
- API: http://localhost:8000 (`/health`, `/ready`, `/docs`, `/v1/meta`)
- MCP: http://localhost:8765/mcp (bearer `MCP_TOKEN`; in the production deploy Caddy serves it at `https://<PUBLIC_HOST>/mcp`)
- FalkorDB: `127.0.0.1:6380`, browser UI at http://localhost:3001

Worker commands: `schema-apply`, `sync-docs`, `sync-history`, `sync-owners`, `sync-tickets`, `derive`, `all`, `stats`, `schedule`, `freshness`, `coordinate`. Add `--force` to re-read sources whose commits are unchanged. `--graph <name>` loads into another graph; `scripts/graph_swap.py` then swaps a `kep_fresh` graph in as `kep` with `GRAPH.COPY`, keeping the previous one as `kep_old`.

## Development

API (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
cd apps/api
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest -m "not integration"
```

Integration tests need a running FalkorDB. With the compose `falkordb` service up, set `FALKORDB_HOST=localhost`, `FALKORDB_PORT=6380` and `FALKORDB_PASSWORD` in the environment, then:

```bash
uv run python -m app.worker schema-apply
uv run pytest -m integration -q
```

To run the API outside Docker: `uv run uvicorn app.main:create_app --factory --reload`. It reads the same environment variables.

Web (Next.js 16, [pnpm](https://pnpm.io/)):

```bash
cd apps/web
pnpm install
pnpm dev          # http://localhost:3000, proxies /api/v1/* to API_INTERNAL_URL (default http://localhost:8000)
pnpm lint
pnpm exec next typegen   # generates the route types tsc needs
pnpm exec tsc --noEmit
pnpm build
```

The web app uses the Geist typefaces and a light and a dark theme (the system preference by default, `t` switches). Keyboard shortcuts are listed in a dialog (`?`) and on the About page; the list lives in `src/lib/shortcuts.ts`. `src/app` also serves `sitemap.xml`, `robots.txt`, a web manifest and an Open Graph image, the landing page carries JSON-LD, and the KEP, SIG and person pages carry breadcrumbs with a matching `BreadcrumbList`.

CI (`.github/workflows/ci.yml`) runs the same commands in four jobs: `api`, `integration` (with a FalkorDB service container), `web` and `compose` (`docker compose config`). A pre-commit config is included.

## Configuration

All settings are read from the environment; `.env.example` lists every one with its default. The important ones:

| Variable | Default | Purpose |
|---|---|---|
| `ENV` | `dev` | `dev`, `test` or `prod` |
| `LOG_LEVEL`, `LOG_FORMAT` | `INFO`, `console` | Logging; `json` for machines |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins, comma-separated |
| `PUBLIC_BASE_URL` | `http://localhost:3000` | Public URL of the web app |
| `FALKORDB_HOST`, `FALKORDB_PORT` | `localhost`, `6380` | Compose overrides these to the `falkordb` service |
| `FALKORDB_PASSWORD` | empty | Required |
| `FALKORDB_ACL_MODE` | `single` | `single` (one password) or `aclfile` (per-role users and passwords) |
| `ENHANCEMENTS_REPO_URL`, `COMMUNITY_REPO_URL`, `OWNERS_REPO_URL` | the public Kubernetes repositories | Sources |
| `ENHANCEMENTS_PIN_SHA`, `COMMUNITY_PIN_SHA`, `OWNERS_PIN_SHA` | empty | Pin a reproducible snapshot; empty means the default-branch head |
| `REPO_CACHE_DIR` | `./repo_cache` | Where the worker keeps its clones |
| `SIGS` | `sig-node,sig-scheduling,sig-apps` | SIG directories in scope |
| `GITHUB_TOKEN` | empty | Read-only token for the GitHub API; required by `sync-owners`, `sync-tickets` and `all` |
| `GITHUB_CACHE` | `auto` | Disk cache of GitHub responses: `auto` (record in `dev`/`test`, off in `prod`), `off`, `record`, `replay` |
| `LLM_FALLBACK_MODELS` | see `.env.example` | Models tried in order when the primary model answers 429/503 |
| `LLM_MODEL`, `LLM_MODEL_CHEAP`, `LLM_FALLBACK_MODELS` | see `.env.example` | Models for the answering agent (OpenAI-compatible endpoint) |
| `LLM_DAILY_BUDGET_USD`, `LLM_REQUESTS_PER_MINUTE`, `LLM_MAX_RETRIES`, `LLM_TIMEOUT_SECONDS` | `5`, `25`, `4`, `60` | Spend and pacing limits |
| `FINDINGS_AGENT_ENABLED`, `FINDINGS_AGENT_DAILY_USD` | `true`, `1` | Switch and daily spend cap for the manual `python -m app.worker freshness` command, which triages findings with the LLM; nothing schedules it |
| `ASK_RATE_LIMIT_PER_10M`, `ASK_DAILY_CAP` | `30`, `150` | Per-client and global limits on `POST /v1/ask` |
| `TOOLS_RATE_LIMIT_PER_10M` | `300` | Per-client limit on `POST /v1/tools/{name}`; 429 answers carry `Retry-After` |
| `TRUST_PROXY` | `false` | Honour `X-Forwarded-For` only behind a trusted proxy |
| `MAX_BODY_BYTES` | `65536` | Request body limit |
| `ADMIN_TOKEN` | empty | Protects admin endpoints such as `DELETE /v1/answers/cache` |
| `MCP_TOKEN`, `MCP_PORT` | empty, `8765` | Bearer token and port for the MCP server |

Production deployment on one VM behind Caddy is described in [docs/ops/DEPLOY.md](docs/ops/DEPLOY.md), with the compose override in `deploy/`.

## Project layout

```
apps/
  api/                 FastAPI service, worker and MCP server (uv, Python 3.12)
    src/app/
      agent/           answering loop, provider adapter, claim validator, answer cache
      api/             /v1 routes
      data/            kep_brain.md, the product document ingested by sync-docs
      db/              FalkorDB pool, batch writer
      eval/            question set loader
      ingest/          sigs, docs, history, owners, tickets, discussion, findings, derive
      mcp/             MCP server (python -m app.mcp)
      memory/          per-user memory graphs and routes
      schema/          label allow-list and schema-apply
      tools/           read-only tool catalog shared by the agent, the API and MCP
      worker/          CLI (python -m app.worker), scheduler, freshness, coordinate
    tests/
  web/                 Next.js 16 app (pnpm)
    src/app/           pages: /, /ask, /explore, /explore/kep/[number], /explore/sig/[key],
                       /explore/person/[login], /audit, /tools, /memory, /eval, /about;
                       sitemap, robots, manifest and Open Graph image
    src/components/    UI, including the evidence chain and its graph drawing
    src/lib/           API client, formatting, routes, keyboard shortcuts
    public/shots/      product screenshots shown on the landing page
deploy/                production compose override and Caddy config
docs/                  README.md (index), DECISIONS.md, AI_USAGE.md, ops/DEPLOY.md, screenshots/
evals/                 question set and hand-check records read by the API
scripts/               graph_swap.py, the blue-green graph swap
docker-compose.yml     falkordb, api, worker, mcp, web
.github/               CI workflow, issue and PR templates, dependabot
```

## API overview

All routes are under `/v1`. Every route reads the `kep` graph only; `POST /v1/ask` additionally writes the answer cache (`ops` graph) and the caller's memory graph, and the `DELETE` routes below write to those two. Interactive docs are at `/docs` when the API is running.

| Method and path | Purpose |
|---|---|
| `GET /v1/meta` | Graph counts, pinned source SHAs, SIGs, releases, LLM status |
| `GET /v1/keps?q=&sig=&status=&limit=` | Search or list KEPs (`q` accepts a number or free text) |
| `GET /v1/keps/{number}` | KEP facts, owners, tracking issue, findings |
| `GET /v1/keps/{number}/history` | Status, stage and milestone changes over time |
| `GET /v1/keps/{number}/decisions` | Derived decisions with deciders and evidence |
| `GET /v1/findings?kind=&sig=&state=` | Findings with a summary by kind and SIG |
| `GET /v1/findings/{key}` | One finding with both sides and evidence |
| `GET /v1/people/{login}` | A person's roles, decisions and activity |
| `GET /v1/sigs`, `GET /v1/sigs/{key}` | SIGs in scope with leadership, KEP and finding counts |
| `GET /v1/changes?since=&sig=&limit=` | What changed since a release |
| `GET /v1/risk?sig=` | Knowledge risk: areas that depend on few people |
| `GET /v1/graph/neighborhood?key=&depth=&limit=` | Nodes and edges around one key, for the lineage graph |
| `GET /v1/tools`, `POST /v1/tools/{name}` | The read-only tool catalog and direct tool calls |
| `POST /v1/ask`, `POST /v1/ask/stream` | Cited answer or abstention; the stream variant uses server-sent events |
| `DELETE /v1/answers/cache` | Clear the answer cache (needs `ADMIN_TOKEN`) |
| `GET /v1/memory/me`, `DELETE /v1/memory/me`, `DELETE /v1/memory/me/facts/{key}`, `DELETE /v1/memory/me/playbooks/{key}` | Per-browser memory, selected by `X-Kep-Memory-Id` |
| `GET /v1/agents/board` | Board written by the manual `worker coordinate` and `worker freshness` commands |
| `GET /v1/sync/status` | Last worker run, step by step |
| `GET /v1/eval/questions`, `GET /v1/eval/latest` | The question set and the latest recorded run |

`GET /health` and `GET /ready` sit outside `/v1`.

The MCP server (`python -m app.mcp`) serves the same tool catalog, minus memory recall and the draft action, plus `get_graph_schema`. Every result is flagged `untrusted_content: true` because graph text comes from public GitHub content. In development it listens on `127.0.0.1:8765`; in the production deploy only Caddy is public and proxies `/mcp` to it (`deploy/Caddyfile`).

## Status

- Data scope is the SIGs listed in `SIGS`; the default instance covers `sig-node`, `sig-scheduling` and `sig-apps`.
- Sources are read live from the default branch unless the `*_PIN_SHA` variables pin them. The pins used by the running instance are shown in `GET /v1/meta`.
- Only public GitHub logins are stored. E-mail addresses in `sigs.yaml` are never read into the graph.
- The draft action writes an issue body for a human to paste. The system never writes to GitHub.
- In `single` ACL mode, read-only enforcement relies on `GRAPH.RO_QUERY` in the application. Per-role users are supported through `FALKORDB_ACL_MODE=aclfile`.
- Design decisions are recorded as ADRs in [docs/DECISIONS.md](docs/DECISIONS.md). Open work is tracked in GitHub issues.

## Contributing

Issues and pull requests are welcome. The project has a single maintainer, so small, focused changes are easiest to review.

1. Open an issue first for anything larger than a small fix. Use the bug report or UI suggestion templates.
2. Run the checks listed in [Development](#development) before opening a pull request. The pull request template lists them.
3. Any fact shown to users must come from the graph with a source URL.
4. Record new design decisions as an ADR in `docs/DECISIONS.md`.

See [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## AI assistance

AI coding assistants were used under human review; see [docs/AI_USAGE.md](docs/AI_USAGE.md).

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

- [FalkorDB](https://www.falkordb.com/) for the graph database and its graph algorithms.
- The Kubernetes community, whose public enhancement, community and OWNERS records make this possible.
- Built during the WeMakeDevs x FalkorDB Graph Hacks hackathon, October 2026.
