# Documentation

| Document | Contents |
|---|---|
| [../README.md](../README.md) | Overview, architecture, graph data model, quick start, configuration and API |
| [ops/DEPLOY.md](ops/DEPLOY.md) | Deploying on one VM with Docker Compose and Caddy, smoke checks, key rotation, graph reload, measured cold start |
| [DECISIONS.md](DECISIONS.md) | Decision log |
| [AI_USAGE.md](AI_USAGE.md) | How AI coding assistants were used and what was checked by hand |
| [screenshots/](screenshots/) | Product screenshots used in the README |
| Design notes (`docs/design/`, cited in code comments as `01 §` to `06 §`) | Removed from the tree on 18 October in commit `fa131f5`; the last version is in git history (`git show fa131f5^:docs/design/03-graph-model.md`) |

The question set, the audit hand-check record, load-test results and one incomplete smoke run (1 question, too few to measure answer quality) are in [../evals/](../evals/). The production compose override and Caddy configuration are in [../deploy/](../deploy/).
