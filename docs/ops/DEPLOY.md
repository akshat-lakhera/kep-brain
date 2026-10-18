# Deploying KEP Brain on one VM

Target: one Linux VM, Docker Engine with the Compose plugin (v2.24 or later, for the `!reset` tag used in `deploy/docker-compose.prod.yml`). Caddy is the only service that publishes ports (80, 443).

## 1. VM

- 2 vCPU, 4 GB RAM, 40 GB disk. FalkorDB is capped at 2 GB (`--maxmemory 2gb`); the web image build needs the remaining headroom.
- Ubuntu 24.04 LTS or similar. Allow inbound 22, 80 and 443 only.
- Create a DNS A record for the public name (below, `PUBLIC_HOST`) pointing at the VM before the first start, so Caddy can obtain a certificate.

## 2. Install Docker

```
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Log out and in again, then check `docker compose version`.

## 3. Clone and configure

```
git clone <repository-url> kep-brain
cd kep-brain
cp .env.example .env
```

Edit `.env`:

- `FALKORDB_PASSWORD`, `ADMIN_TOKEN`, `MCP_TOKEN`: long random values, for example `openssl rand -hex 32`. Compose refuses to start without `FALKORDB_PASSWORD` and `MCP_TOKEN`.
- `OPENAI_API_KEY`: key for the OpenAI-compatible endpoint in `OPENAI_BASE_URL`. Without it `/v1/ask` returns 503.
- `GITHUB_TOKEN`: required. `sync-owners` and `sync-tickets` read the GitHub API and `worker all` stops with an error without it (the image has no `gh` CLI). A classic token with no scopes, or a fine-grained read-only token, is enough.
- `ENHANCEMENTS_PIN_SHA`, `COMMUNITY_PIN_SHA`, `OWNERS_PIN_SHA`: leave empty. The worker clones the public repositories on its first run and fetches them on every sync, so the graph follows the upstream default branches. Set them only for a reproducible snapshot.
- `PUBLIC_HOST=<dns name>`: used by the prod override and Caddy. Compose reads it from `.env` in the project directory.
- `REPO_CACHE_HOST`: leave unset on the VM (a named volume is used).

The prod override sets `ENV=prod` for the api and the worker (so the worker reads GitHub fresh on every sync instead of replaying its disk cache of responses, as `dev` and `test` do), and `CORS_ORIGINS=https://${PUBLIC_HOST}` and `PUBLIC_BASE_URL=https://${PUBLIC_HOST}` for the api, so these values in `.env` are ignored. Keep `GITHUB_CACHE` at `auto` (or `off`); `record` or `replay` in `.env` would bring the cache back. `FALKORDB_HOST` and `FALKORDB_PORT` are set by compose.

Shorthand used below:

```
export COMPOSE="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"
$COMPOSE config --quiet
```

## 4. First data load

The worker needs a populated graph before the api has anything to serve. This starts FalkorDB, builds the image and runs the full pipeline. On a fresh server the first run also clones kubernetes/enhancements and kubernetes/community into the cache volume (allow several extra minutes; later runs only fetch) and reads the OWNERS files from the GitHub API. Ticket sync is rate-limited by GitHub:

```
$COMPOSE run --rm worker all
```

The data lives in the `kep-brain_falkordb-data` volume. The `worker` service runs the pipeline once when it starts, then again 1440 minutes after each run finishes. After each successful sync it also runs one coordination tick (triage open findings, draft stale-issue updates, verify the drafts) when `FINDINGS_AGENT_ENABLED` is true and `OPENAI_API_KEY` is set; LLM spend stays within `FINDINGS_AGENT_DAILY_USD` per day, and a failed tick is logged without stopping the schedule.

## 5. Start

```
$COMPOSE up -d --build
$COMPOSE ps
```

All services should report `healthy` (worker has its healthcheck disabled). Caddy requests the certificate on first start; check `$COMPOSE logs caddy` if HTTPS does not answer within a minute.

## 6. Smoke checks

Run from a machine outside the VM:

```
curl -fsS https://$PUBLIC_HOST/v1/meta
curl -fsSI https://$PUBLIC_HOST/
curl -fsS -X POST https://$PUBLIC_HOST/v1/ask -H 'content-type: application/json' -d '{"question":"Which KEPs are owned by sig-node?"}'
```

The last request needs a working LLM key (`question` is 3 to 1000 characters; the API docs page is disabled when `ENV=prod`). Set `PUBLIC_HOST` in the shell first (`export PUBLIC_HOST=<dns name>`). Confirm nothing else is public: ports 3000, 3001, 6380, 8000 and 8765 must be closed from outside (`nmap -p 3000,3001,6380,8000,8765 $PUBLIC_HOST`), and on the VM `ss -ltn` shows listeners only on 22, 80 and 443.

MCP is reached only through Caddy, which proxies `/mcp` to the `mcp` service (`deploy/Caddyfile`); the service itself publishes no port. A request without the bearer token must be rejected:

```
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://$PUBLIC_HOST/mcp -H 'content-type: application/json' -d '{}'   # 401
```

## 7. Rotate the LLM key

```
nano .env                       # replace OPENAI_API_KEY
$COMPOSE up -d --force-recreate api worker mcp
```

`env_file` is read at container creation, so a plain restart does not pick up the change. Revoke the old key at the provider after `/v1/meta` and an `/v1/ask` call succeed.

## 8. Reload the graph (blue-green swap)

The scheduled worker upserts into the live `kep` graph. For a full reload (new `SIGS`, a bumped `INGEST_VERSION`, a suspect graph) load next to it and swap:

```
$COMPOSE run --rm worker all --graph kep_fresh
$COMPOSE run --rm -v "$PWD/scripts:/scripts:ro" --entrypoint python api /scripts/graph_swap.py --dry-run
$COMPOSE run --rm -v "$PWD/scripts:/scripts:ro" --entrypoint python api /scripts/graph_swap.py
```

The script is not part of the image, so it is mounted into a one-off `api` container, which has the FalkorDB client and the same `FALKORDB_*` variables as the API. `scripts/graph_swap.py` copies the live graph to `kep_old` (`GRAPH.COPY`), replaces `kep` with `kep_fresh` and clears the answer cache. Between the `GRAPH.DELETE kep` and the copy, reads answer empty for a moment. Check the counts in `/v1/meta`, then delete `kep_old` when satisfied.

## 9. Update

```
git pull
$COMPOSE up -d --build
```

This recreates changed services; a recreated worker starts a sync at once. When that run has finished (`last_run.finished_at_iso` in `/v1/sync/status` is after the update), the `sync-tickets` step should show `cache_hits` 0.

## Measured cold start

Fresh cache and an empty graph, one worker process per step, GitHub token with read access to public repositories (a classic token with no scopes, or a fine-grained read-only token, is enough; the sync only reads public data). Measured on 2026-10-15 with the concurrent ingest (one run each; GitHub clone speed varies by several minutes between runs):

| Step | Cold (empty graph, empty cache) | Warm (same graph, nothing changed upstream) |
|---|---|---|
| schema-apply | 7 s | - |
| sync-docs | 342 s, of which the two clones took about 290 s | 6 s (skipped, commits unchanged) |
| sync-history | 48 s | 8 s (skipped, commits unchanged) |
| sync-owners | 37 s (176 REST requests, fetched in parallel) | 7 s |
| sync-tickets | 556 s (122 GraphQL points; 233 issues, one issue per query) | 26 s (3 points; only issues updated since the last run) |
| derive | 6 s | 5 s |
| total | about 17 minutes | about 1 minute |

An earlier serial run of the same steps took about 19 minutes, with sync-owners at 158 s and sync-tickets at about 780 s. The cold graph matched a graph loaded serially node for node (apart from upstream activity in between). `--force` on the worker re-reads sources whose commits did not change.
