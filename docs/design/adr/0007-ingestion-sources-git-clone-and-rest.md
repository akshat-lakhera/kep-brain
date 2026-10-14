# ADR 0007 · Ingestion: KEP documents from a git clone; threads, reviews and history from batched GraphQL; REST for lists and contents

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Decider: not yet ratified; H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 (file name kept for stable links) |
| Veto-able | Yes (bot account vs GitHub App; GraphQL batch size; P1 on or off) |
| Related | `02-architecture.md` §9; `01-recon-kubernetes-data.md` §3, §6; ADR 0008, ADR 0019, ADR 0020 |

## Context

The doc layer is `kubernetes/enhancements`: 686 `kep.yaml` files (684 parseable; 232 in the chosen SIGs), READMEs and 481 PRR files (`01` §3). Decision tracing needs each `kep.yaml`'s history with the commit and PR that changed it. Tickets and chats exist only through the GitHub APIs.

Budget facts (VERIFIED 2026-10-12): PAT requests "count towards your personal rate limit of 5,000 requests per hour" and a GitHub App installation has a "minimum rate limit of 5,000 requests per hour" (https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api); a GraphQL call costs the sum of connection requests divided by 100, rounded, minimum 1, with 5,000 points per hour per user, at most 500,000 nodes per call, and extra points deducted after a timeout (https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api). The recon observed REST `events`/`timeline` silently dropping label events after 2022 on #1287 while GraphQL returned all 96 (`01` §6.4).

The v1 design fetched PR files, reviews and per-item comments by REST: ≈ 5,750 requests for P0 (over the hourly limit, 1.5–2 h with a forced reset wait) and ≈ 12,500 with P1 (≈ 3 h). It also ran under a "dedicated PAT" that, if minted on a member's account, shares that member's budget.

## Decision

- **Doc layer from git**: full clone of `kubernetes/enhancements` on the `repo_cache` volume, pinned `head_sha`, `git ls-tree -r` rooted at `keps/` (symlink entries recorded as aliases; test-fixture `kep.yaml` files under `pkg/*/testdata/` never become KEPs), history with `git log` (never author or committer e-mail formats) and `git show`. Zero API calls.
- **Commit → PR**: `Merge pull request #N` subjects; otherwise GraphQL `object(oid:)` → `associatedPullRequests(first: 1)`, 50 commits per query.
- **Discovery by REST**: `issues?state=all&labels=sig/<x>&sort=updated&direction=asc&since=…&per_page=100` with `If-None-Match`; repo-wide `issues/comments?since=` for incremental comments; contents API (raw media type, ETags) for `sigs.yaml`, `OWNERS_ALIASES` and the 95 `OWNERS` files; releases list.
- **Threads, reviews, files and label history by GraphQL**, serial, 25 items per query by alias: tracking issues with `timelineItems(first: 100, itemTypes: [LABELED_EVENT, UNLABELED_EVENT, MILESTONED_EVENT, DEMILESTONED_EVENT, CROSS_REFERENCED_EVENT])` (requesting `id`) and `comments(first: 100)`; PRs with `files`, `reviews`, `comments` (`first: 100` each); cursor pagination beyond 100; batch size drops to 10 after a GraphQL timeout.
- **P1** (`kubernetes/kubernetes` items referencing a tracking issue) is off by default (`TICKETS_SCOPE=p0`); when on, it is fetched with `nodes(ids:)` in batches of 50 and is a **load-time snapshot**, stated in the freshness block and README, because new k/k comments do not move the tracking issue's `updated_at`.
- **Identity**: a dedicated bot GitHub account with two read-only fine-grained PATs (`dev` for the seed load, `vm` for incremental sync) and the separate action PAT of ADR 0021. Never a team member's token.
- **Dev cache**: `GITHUB_RAW_CACHE_MODE=record|replay|off` on a local named volume `github_cache`; never committed.
- **VM seeding**: the full load runs once on the dev machine in a clean Compose project; the VM is restored from that dump and runs incremental sync only.
- **Pacing**: strictly serial; REST headers and GraphQL `rateLimit { cost remaining resetAt }` read on every response; sleep to reset below 50 remaining; `retry-after` honoured; exponential backoff 1–60 s (tenacity 9.2.1), 7 attempts, then the run fails with cursors intact.

**Budget (INFERENCE; measured in ING-03):** full P0 ≈ 130 REST requests + ≈ 340 GraphQL points (≤ 2,600 points even at the recon's conservative pricing), ≈ 15–20 minutes serial; P1 ≈ 150 points (≤ 1,400 conservative), ≈ 10 minutes; steady state ≤ 40 REST requests per hour. Table per endpoint in `02-architecture.md` §9.4.

## Alternatives considered

- REST for everything (v1): ≈ 5,750–12,500 requests, 1.5–3 hours, and a forced rate-limit wait inside the CP3 window.
- A GitHub App installation: its own minimum 5,000 requests per hour; rejected as default because it adds JWT and installation-token code for a budget the batched design does not need. The upgrade path if the bot account is ever rate-limited.
- Re-running the full load on the VM (v1's INF-05): doubles the spend for no new data.
- Committing the raw-response cache for reproducible dev runs: rejected, because issue and PR comments are never committed (`01` D11, ADR 0020).
- Reading the tree through the contents API instead of a clone: loses `git log`/`git show` history.

## Consequences

- The full ticket load fits easily inside CP3's window; a forced rate-limit sleep is no longer on the critical path.
- The ING-03 "second run" test is incremental: with no upstream change a `schedule` tick finishes in under 30 s using `since` cursors and 304s.
- Fine-grained PAT support for GraphQL reads is UNVERIFIED until INF-02 (Oct 15); fallback: a classic PAT with no scopes on the same bot account.

## Revision 2026-10-12

PR files, reviews and comments, tracking-issue comments and commit → PR fallback moved from REST to batched GraphQL; per-endpoint budget recomputed; bot-account identity; dev cache volume; VM seeding; P1 snapshot semantics (design review R12, R15).
