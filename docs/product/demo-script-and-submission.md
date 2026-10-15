# Demo script and submission answers

Status: matches the product as built on 2026-10-15. Counts below were read from `GET /v1/meta` and `GET /v1/findings` on the local API; re-read them on the deployed site before recording, because they change when the worker re-syncs. Items written `[FILL: ...]` are for a human.

## Numbers used in the video and the form

| Item | Value | Source |
|---|---|---|
| KEPs in the graph | 238 (sig-node, sig-scheduling, sig-apps) | `/v1/meta` `graph.keps` |
| Graph size | 27,008 nodes, 102,558 edges, 613 people | `/v1/meta` `graph` |
| Findings | 59 across 50 KEPs | `/v1/findings` `summary` |
| By kind | 40 active_status_closed_issue, 8 stage_mismatch, 7 milestone_mismatch, 3 one_sided_replacement, 1 terminal_status_future_targets | `summary.by_kind` |
| By SIG | sig-node 30, sig-scheduling 20, sig-apps 9 | `summary.by_sig` |
| Tickets as of | 2026-10-14T19:11:54Z | `/v1/meta` `sources` |
| Eval results | not measured yet; `GET /v1/eval/latest` returns not_found | README Results table |

Do not quote eval accuracy, latency or recall in the video or the form until the README table has numbers.

## 3-minute video script

Target 2:50, hard cap 3:00. Record the deployed site, not localhost. One take per segment, cursor visible, no music.

| Time | On screen | Narration |
|---|---|---|
| 0:00 | `/audit`, summary line | "Kubernetes keeps its design decisions in KEPs. The kep.yaml file, the tracking issue and the replaces data are supposed to agree. This graph has 238 KEPs from three SIGs, and 59 findings across 50 of them where they do not." |
| 0:20 | Filter by kind `active_status_closed_issue` | "The largest group, 40 findings, is a KEP whose kep.yaml says it is still active while its tracking issue is closed." |
| 0:35 | Expand the row for KEP 1591 | "Open a row. On one side kep.yaml says implementable. On the other, issue 1591 was closed as completed on 2023-01-12. Each side links to the exact file or issue at the pinned commit." |
| 1:00 | Press `d`, show the draft dialog | "Draft fix builds an issue body that lists both values and every evidence URL. It never posts to GitHub; a person copies it." |
| 1:25 | Click through to `/explore/kep/1591` | "The KEP page shows its facts, its status history and the decisions behind each state. A decision links a status change to the pull request that made it, and to the people who approved and merged it." |
| 1:55 | Lineage graph on the KEP page, then a `one_sided_replacement` finding | "The lineage graph follows replaces and superseded-by. Three findings are replacements recorded on only one side." |
| 2:15 | `/`, ask one question about a KEP's approver | "Questions go to a model that can only call graph tools. The answer shows its steps and cites graph nodes. A validator rejects a claim with no node behind it, and the system abstains instead." |
| 2:40 | README FalkorDB table | "FalkorDB is the only store. Reads go through GRAPH.RO_QUERY with timeouts, ingest is MERGE-based and idempotent, UNIQUE and MANDATORY constraints guard the keys, edges carry valid_from and valid_to, and each user's memory is its own graph." |
| 2:55 | Title card with the live URL | "Live demo and code are linked below." |

Before recording: rehearse the ask question once on the deployed site and choose one that returns a cited answer; the free LLM tier is rate-limited. If it abstains on camera, say so.

Recording checks: video at most 3:00 on YouTube; the live site opens without sign-up; every number spoken matches the table above; no secret or `.env` value on screen; the draft dialog shows that nothing is posted.

## Submission form answers

The form fields are not published; map these to the real fields when the form opens.

### Project summary

KEP Brain audits Kubernetes decision records for contradictions. It loads the KEPs of sig-node, sig-scheduling and sig-apps (238 KEPs), their tracking issues, the pull requests and reviews that changed their status, and the people involved, into one FalkorDB graph of 27,008 nodes. It reports 59 findings across 50 KEPs where kep.yaml, the tracking issue and the replaces data disagree, shows who decided each state and from which evidence, and drafts the fix as an issue body without posting it. Questions are answered by an agent restricted to graph tools; every claim must cite a graph node with a public GitHub URL or the system abstains.

### How FalkorDB was used

FalkorDB 4.22.0 is the only store. The graph `kep` holds the data; each user's memory is a separate graph named `mem:<ULID>`.

- Writes: `UNWIND` plus `MERGE` batches in `apps/api/src/app/db/batch.py`, so the worker can be re-run; stale edges are closed or deleted per run.
- Reads: every request path uses `GRAPH.RO_QUERY` with a 2000 ms timeout (`db/falkordb.py`, `tools/base.py`).
- Schema: range indexes, `UNIQUE` constraints on `key` for every label and `MANDATORY` constraints on required properties (`schema/apply.py`).
- Queries: pattern comprehensions return a KEP with its current issue, owners and evidence in one statement; temporal `valid_from` and `valid_to` edges separate current from historical state.
- Algorithms: `algo.SPpaths` powers the `path_between` tool (`tools/t01/graph_algos.py`).
- Memory: one graph per memory id, deletable as a unit (`memory/store.py`).

Full table with file paths: README section "How FalkorDB is used".

### Feedback on FalkorDB

- In 4.22.0, two pattern comprehensions in one projection that reuse a local variable name make the later one return an empty list, with no error. We rename local variables per comprehension (`tools/cypher.py`).
- Graph names cannot be parameters, so we validate the id before building `mem:<id>`.
- `UNIQUE` constraints need the exact-match index first; creation order matters, and `MANDATORY` can only be applied once existing nodes satisfy it.
- With a single password, read-only enforcement depends on the application using `GRAPH.RO_QUERY`.

### Tracks

Track 3 (Company Brain) is the master track: audit, KEP page, cited answers. Track 1 layers on the same tool catalog: `path_between`, `rank_people`, the draft-issue action, and a read-only MCP server. Track 2 adds per-user memory graphs, shared finding memory and a freshness agent. Routes and endpoints are listed in the README "Track coverage" table.

### AI-assistance disclosure

AI coding assistants drafted code and documentation under human direction; humans set the design, reviewed every change and ran the tests. Each use is logged in `docs/AI_USAGE.md`. At runtime a Groq-hosted model plans tool calls and drafts answers, and a deterministic validator checks every claim against graph rows. Design notes pre-date the event; the first commit is documentation only. See README "Provenance".

### Other fields

| Field | Answer |
|---|---|
| Repository | [FILL: public GitHub URL] |
| Live demo | [FILL: deployed URL]; no sign-up |
| Video | [FILL: YouTube URL, at most 3:00] |
| Tech stack | FalkorDB 4.22.0, FastAPI (Python 3.12), Next.js, own MCP server, Groq through an OpenAI-compatible adapter |
| Team and contributions | [FILL: names and one concrete paragraph each] |
| What is next | Widen to all SIGs by configuration; run and publish the eval; compute stored PageRank and betweenness for `rank_people` |
| Limits | Eval numbers not measured; the LLM tier is rate-limited, so answers can be slow or abstain |
