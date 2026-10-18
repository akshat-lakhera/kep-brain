# KEP Brain
<!-- readme: kep-brain -->

KEP Brain is a company brain for the Kubernetes enhancement process. It loads KEPs (Kubernetes Enhancement Proposals), SIG rosters, tracking issues and pull request history from public GitHub into one graph, works out who decided what and on which evidence, flags records that contradict each other, and answers questions with citations or abstains. "KEP Brain", "kep brain" and "this tool" name the same product. It is an independent open-source project by one developer.

## What KEP Brain answers
<!-- readme: the-problem -->

KEP Brain answers who decided a KEP's current state and on what evidence, who approved a KEP, who owns or knows an area, what replaced what, what changed since a release, and which records are stale or disagree. It also explains what a KEP, a status, a stage or a kep.yaml field means, from the process documents stored in the graph. Explore pages show KEPs with their facts, status history, decisions and lineage, SIGs with their leadership and KEPs, and people with their roles.

## How answers are produced
<!-- readme: how-it-works -->

A question goes to a language model that may only call read-only graph tools. Every tool result is a set of graph records, each with an evidence id and a public GitHub URL. A deterministic validator checks every cited claim against the records returned in that request: a citation it cannot tie to a record is unsupported, an answer without a valid citation is not accepted, and in either case the whole answer is replaced by an abstention. Explicit mentions of returned KEPs, issues and people are linked to their records automatically. KEP Brain never answers from outside knowledge. Answers are cached per question and graph version.

## When KEP Brain abstains
<!-- readme: how-it-works -->

KEP Brain abstains instead of guessing. The abstention reasons are no_evidence (the graph holds nothing relevant), out_of_scope (not about KEPs, the KEP process, the loaded SIGs or KEP Brain itself), unsupported_claims (the draft answer made a claim no returned record backs), budget_exhausted (the answering budget ran out before an answer was checked) and graph_unavailable (the graph database did not answer).

## What the audit does
<!-- readme: what-it-does -->

Five checks compare a KEP's kep.yaml with its tracking issue and its replacement declarations: active_status_closed_issue, terminal_status_future_targets, one_sided_replacement, stage_mismatch and milestone_mismatch. Each disagreement is a Finding that keeps both records with their public source URLs, who set each value, a suggested fix and a lifecycle. The audit page can draft an issue text from that evidence for a human to review. Nothing is ever posted to GitHub.

## How the graph is built
<!-- readme: how-it-works -->

The worker reads every kep.yaml, KEP README and production readiness review file from the kubernetes/enhancements clone and replays each revision, so state edges carry the interval they were valid for; "current" and "as of release X" are the same graph with a different filter. Field changes become StatusChange nodes linked to their commit and pull request, Decision nodes are derived from them and linked to the people who decided and the evidence, and the five checks write Finding nodes. Every run upserts into the same graph, so re-running is safe.

## Data sources and scope
<!-- readme: status -->

KEP Brain reads kubernetes/enhancements (KEPs, kep.yaml files, the KEP process documents), kubernetes/community (sigs.yaml rosters) and OWNERS files from kubernetes/kubernetes, plus tracking issues, timelines, pull requests and review threads through the GitHub API. The SIGs in scope are configured; the default instance covers sig-node, sig-scheduling and sig-apps, and other SIGs have no KEP data loaded. The data is as fresh as the last worker run. Every record links back to its public GitHub source.

## Tools, API and MCP
<!-- readme: api-overview -->

Every answer is produced through a catalog of read-only graph tools that can also be called directly, one by one, with their parameters. The same catalog is served over HTTP under /v1 and over the Model Context Protocol (MCP) behind a bearer token, so other agents can query the graph. Every route reads the graph with read-only queries; the only writes of the API are the answer cache and the caller's own memory.

## Privacy
<!-- readme: status -->

KEP Brain stores only public GitHub logins and the public roles they hold; e-mail addresses are never ingested. It has no accounts, sets no cookies and loads no analytics or other third-party script. The text of a question and the graph rows read for it are sent to the configured model provider to compose the answer. The API does not write question text to its logs.

## Memory
<!-- readme: what-it-does -->

An anonymous memory id generated in the browser selects a small per-user graph that remembers answered questions, the records they cited and the tools used. It can be inspected and deleted as a unit on the Memory page; the API also deletes single facts and playbooks. No other visitor can read it, and nothing else about a visitor is stored.

## Licence
<!-- readme: license -->

The KEP Brain code is open source under the MIT licence. The data it reads, KEP texts, metadata and issues, is written by The Kubernetes Authors and published under the Apache License 2.0; KEP Brain reads it in place, links back to it and changes nothing upstream. The software is provided as is, without warranty of any kind.

## Affiliation
<!-- readme: top -->

Kubernetes is a trademark of The Linux Foundation. KEP Brain is an independent open-source project by one developer and is not affiliated with, or endorsed by, the Kubernetes project, the CNCF or FalkorDB.
