# ADR 0017 · Single-VM Docker Compose deployment with Caddy TLS, host-cron backups and dump seeding

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12; adopts `06-build-plan.md` B9 as superseded by B16, and C9). Provider and domain are the team's call at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Yes: VM provider, size, domain, Railway or Fly instead |
| Related | `02-architecture.md` §4, §13; ADR 0002, ADR 0007 |

## Context

Rule 10 prefers a live deployment; past-event tips say the live demo must work without sign-up and stay up through judging. FalkorDB Cloud's free tier stops after one day idle and has no persistence. FalkorDB documents Compose with persistence and healthchecks (https://docs.falkordb.com/operations/docker) and Railway templates (https://docs.falkordb.com/operations/railway). `caddy:2.11.7` (2026-10-03) provides automatic TLS. The dev host is Windows 11 with ports 6379 and 5432 taken by unrelated containers.

## Decision

- **Dev**: root `docker-compose.yml` (generated after kickoff, ADR 0023): `acl-init`, `falkordb` (`falkordb/falkordb:v4.22.0`, `127.0.0.1:6380`, Browser `127.0.0.1:3001`), `api` (8000), `worker`, `mcp` (`127.0.0.1:8765`), `web` (3000); networks `edge` and `data`; volumes `falkordb_data`, `repo_cache`, `github_cache`. Nothing on 6379 or 5432.
- **Prod**: one VM (3 vCPU / 4 GB / 80 GB class, e.g. Hetzner CPX21; Ubuntu 24.04 LTS; Docker Engine + Compose plugin; `ufw` 22/80/443) running the standalone `deploy/compose.prod.yml` (B16): `caddy:2.11.7` (the only service with `ports:`), `web`, `api`, `mcp`, `worker`, `acl-init`, `falkordb/falkordb-server:v4.22.0` (no published ports). Images from GHCR by `sha-<short>` tag; deploy by a manual `workflow_dispatch` job over SSH.
- **Seeding**: the VM is restored from a dump of a clean seed load made on the dev machine, then runs incremental sync only (ADR 0007).
- **Backups**: a host cron entry, nightly 02:00 UTC: `BGSAVE` as `default`, wait for completion, copy `dump.rdb` and `appendonlydir/` to `/backups/<UTC timestamp>/`, keep 7; also before any full reload. Restore runbook in `docs/RUNBOOK.md`, rehearsed once on the VM (INF-06).
- **Uptime**: `restart: unless-stopped`, healthchecks, `noeviction`, an external 5-minute ping on `/` and `/api/v1/meta`.
- **Domain**: a real domain for Let's Encrypt; fallback `<ip>.sslip.io`.

## Alternatives considered

- A backup sidecar container (v1): one more service and image for a nightly command the host can run.
- Railway: FalkorDB's template plus our services; plan B. Rejected as default because the ACL-file init and the worker's git volume are easier to reason about in one Compose file.
- Fly.io: similar reasoning. Kubernetes: far beyond four days. FalkorDB Cloud free tier: idle stop, no persistence.

## Consequences

- One `docker compose up` reproduces the dev stack for a judge; production differs only by the edge proxy, image and network layout (drift test, B16).
- Whether Redis loads the RDB when AOF is enabled and absent is UNVERIFIED until the restore drill; the fallback is in `02` §13.4.

> **Superseded content (v1 of this ADR).** v1 named the dev file `deploy/compose.dev.yaml` with host ports 16379 and 13000 and ran a backup sidecar; replaced by the root `docker-compose.yml`, ports 6380/3001 and host cron.

## Revision 2026-10-12

File names and ports per `06` C9; standalone prod file per B16; `agent` service; host-cron backups; dump seeding (design review R6, R7, R12, R15, R16).
