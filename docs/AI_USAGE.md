# AI usage

AI coding assistants are used in this project to draft code and documentation under human direction. Humans set the design, decide the scope, review every change before it is committed, and run the tests. Facts shown to users come from the graph, not from model memory.

Every pull request adds a row to the table below.

| Date | Area | What the AI did | What the human checked |
|---|---|---|---|
| 2026-10-15 | Scaffold | Set up project layout, tooling configuration and settings on top of the generator output | Generator output was committed unmodified first; diffs and pinned versions were reviewed against the build plan |
| 2026-10-15 | API core | Drafted settings, error envelope, request-id middleware, FalkorDB role pool and batch writer | Reviewed against the design notes; unit tests run, integration tests run against a local FalkorDB with a throwaway graph |
| 2026-10-15 | Infra and docs | Drafted Dockerfiles, CI workflow, `.env.example`, README and this log | Compared `.env.example` with `settings.py`; validated `docker compose config`; built the API image |
| 2026-10-15 | README and submission docs | Rewrote the README and the demo script and form answers from the code and the live API | File paths in the FalkorDB table were checked by grep; counts were read from `/v1/meta` and `/v1/findings`; claims that could not be verified were left out |
